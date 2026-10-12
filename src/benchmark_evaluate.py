"""Generic FindBack benchmark evaluator (read-only).

Compares context-only, TF-IDF + context, and Sentence-BERT + context
on a labeled benchmark without touching app or matching code.

Context/location/time/category scoring mirrors src/matcher.py weights;
this file intentionally duplicates that logic so importing it never
triggers the app dataset load and existing files stay unchanged.

Usage (benchmark mode):
    python src/benchmark_evaluate.py --lost benchmark/dev/lost.csv \\
        --found benchmark/dev/found.csv --labels benchmark/dev/labels.csv

Smoke test on existing synthetic CSV (same file as both inputs):
    python src/benchmark_evaluate.py --lost dataset/findback_reports.csv \\
        --found dataset/findback_reports.csv --labels <labels csv>

Labels CSV: lost_id,expected_found_id,has_match  (has_match optional,
defaults to 1; empty expected id + has_match=0 = no-valid-match case).

Metrics per method: Top-1 / Top-3 / Top-5, MRR, nDCG@top_n over
has_match=1 queries. With --threshold, a query whose top score is
below the threshold abstains ("No Strong Match"): counted as a miss
for ranking metrics, and correct for has_match=0 queries.
"""

import argparse
import math
import os
import re
import sys

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

TOP_N_DEFAULT = 5

# Same weights as the live app: desc 0.50 / loc 0.25 / time 0.15 / cat 0.10.
W_DESC, W_LOC, W_TIME, W_CAT = 0.50, 0.25, 0.15, 0.10
# Context-only renormalisation of the non-description weights (0.25+0.15+0.10=0.50).
W_LOC_C, W_TIME_C, W_CAT_C = 0.50, 0.30, 0.20


def clean_text(text):
    text = str(text).lower().replace("-", " ")
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def norm_value(value):
    if pd.isna(value):
        return ""
    return str(value).strip().lower()


def location_similarity(lost, found):
    weights = {"organization_name": 0.30, "campus_or_branch": 0.15,
               "building_or_terminal": 0.20, "floor_or_level": 0.10,
               "specific_area": 0.25}
    total, matched = 0.0, 0.0
    for field, w in weights.items():
        a, b = norm_value(lost.get(field, "")), norm_value(found.get(field, ""))
        if not a or not b:
            continue
        total += w
        if a == b:
            matched += w
        elif a in b or b in a:
            matched += w * 0.90
        else:
            from difflib import SequenceMatcher
            r = SequenceMatcher(None, a, b).ratio()
            if r >= 0.80:
                matched += w * 0.75
            elif r >= 0.60:
                matched += w * 0.50
    return matched / total if total else 0.0


def time_similarity(lost, found):
    a_date, a_time = norm_value(lost.get("date", "")), norm_value(lost.get("approx_time", ""))
    b_date, b_time = norm_value(found.get("date", "")), norm_value(found.get("approx_time", ""))
    if not a_date or not a_time or not b_date or not b_time:
        return 0.0
    try:
        a = pd.to_datetime(a_date + " " + a_time)
        b = pd.to_datetime(b_date + " " + b_time)
    except Exception:
        return 0.0
    mins = abs((b - a).total_seconds() / 60)
    if mins <= 30:
        return 1.0
    if mins <= 60:
        return 0.8
    if mins <= 120:
        return 0.5
    if mins <= 360:
        return 0.25
    if mins <= 1440:
        return 0.10
    return 0.0


def category_similarity(lost, found):
    a, b = norm_value(lost.get("item_category", "")), norm_value(found.get("item_category", ""))
    if not a or not b:
        return 0.0
    return 1.0 if a == b else 0.0


def load_csv(path, dtype=str):
    df = pd.read_csv(path, dtype=dtype).fillna("")
    # Skip format-validation placeholders.
    if "report_id" in df.columns:
        df = df[~df["report_id"].str.startswith("EXAMPLE-")]
    if "lost_id" in df.columns:
        df = df[~df["lost_id"].str.startswith("EXAMPLE-")]
    return df.reset_index(drop=True)


def rank_candidates(lost, found_df, desc_scores, method):
    scored = []
    for i, (_, frow) in enumerate(found_df.iterrows()):
        found = frow.to_dict()
        loc = location_similarity(lost, found)
        tim = time_similarity(lost, found)
        cat = category_similarity(lost, found)
        if method == "context":
            final = loc * W_LOC_C + tim * W_TIME_C + cat * W_CAT_C
        else:
            final = desc_scores[i] * W_DESC + loc * W_LOC + tim * W_TIME + cat * W_CAT
        scored.append((found.get("report_id", ""), final))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def ndcg_at_k(rank, k):
    if rank is None or rank > k:
        return 0.0
    return 1.0 / math.log2(rank + 1)


def evaluate_method(lost_df, found_df, labels, desc_scores_fn, method, top_n, threshold):
    hits1 = hits3 = hits5 = rr_sum = ndcg_sum = 0
    n_match = 0
    abstain_correct = abstain_total = 0
    details = []

    for _, lab in labels.iterrows():
        lost_id = str(lab["lost_id"])
        expected = str(lab.get("expected_found_id", "")).strip()
        has_match = int(lab.get("has_match", 1)) if "has_match" in lab else 1

        lrows = lost_df[lost_df["report_id"].astype(str) == lost_id]
        if lrows.empty:
            continue
        lost = lrows.iloc[0].to_dict()
        desc_scores = desc_scores_fn(lost, found_df)
        ranked = rank_candidates(lost, found_df, desc_scores, method)
        top_ids = [r[0] for r in ranked[:top_n]]
        top_score = ranked[0][1] if ranked else 0.0
        abstained = threshold is not None and top_score < threshold

        if has_match == 0:
            abstain_total += 1
            if abstained:
                abstain_correct += 1
            details.append({"lost_id": lost_id, "expected": "",
                            "top1": top_ids[0] if top_ids and not abstained else "ABSTAIN",
                            "rank": "N/A (no match)", "top_score": top_score,
                            "abstained": abstained})
            continue

        n_match += 1
        rank = top_ids.index(expected) + 1 if (expected in top_ids and not abstained) else None
        if rank is not None:
            if rank <= 1:
                hits1 += 1
            if rank <= 3:
                hits3 += 1
            if rank <= 5:
                hits5 += 1
            rr_sum += 1.0 / rank
            ndcg_sum += ndcg_at_k(rank, top_n)
        details.append({"lost_id": lost_id, "expected": expected,
                        "top1": top_ids[0] if top_ids and not abstained else "ABSTAIN",
                        "rank": rank if rank else f"Not in Top {top_n}",
                        "top_score": top_score, "abstained": abstained})

    n = max(n_match, 1)
    return {"method": method, "n_match": n_match, "n_no_match": abstain_total,
            "top1": hits1 / n, "top3": hits3 / n, "top5": hits5 / n,
            "mrr": rr_sum / n, "ndcg": ndcg_sum / n,
            "abstain_acc": (abstain_correct / abstain_total) if abstain_total else None,
            "details": details}


def main():
    ap = argparse.ArgumentParser(description="Evaluate FindBack matchers on a labeled benchmark.")
    ap.add_argument("--lost", required=True)
    ap.add_argument("--found", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--methods", default="all",
                    help="comma list of context,tfidf,semantic or 'all'")
    ap.add_argument("--top-n", type=int, default=TOP_N_DEFAULT)
    ap.add_argument("--threshold", type=float, default=None,
                    help="scores below this abstain ('No Strong Match')")
    ap.add_argument("--output", default=None, help="optional per-query CSV output")
    args = ap.parse_args()

    for p in (args.lost, args.found, args.labels):
        if not os.path.exists(p):
            print(f"ERROR: file not found: {p}")
            return 2

    lost_df = load_csv(args.lost)
    found_df = load_csv(args.found)
    labels = pd.read_csv(args.labels, dtype=str).fillna("")
    if "lost_id" not in labels.columns:
        print("ERROR: labels CSV needs columns lost_id,expected_found_id,has_match")
        return 2
    if "expected_found_id" not in labels.columns:
        labels["expected_found_id"] = ""
    if "has_match" not in labels.columns:
        labels["has_match"] = "1"
    labels = labels[~labels["lost_id"].str.startswith("EXAMPLE-")]

    # Keep only Lost queries / Found candidates when report_type is present.
    if "report_type" in lost_df.columns:
        lost_df = lost_df[lost_df["report_type"].str.lower() == "lost"].reset_index(drop=True)
    if "report_type" in found_df.columns:
        found_df = found_df[found_df["report_type"].str.lower() == "found"].reset_index(drop=True)

    if lost_df.empty or found_df.empty or labels.empty:
        print("No evaluable rows (only EXAMPLE placeholders?). "
              "Add real labeled data first - nothing was scored.")
        return 0

    methods = [m.strip() for m in args.methods.split(",")]
    if methods == ["all"]:
        methods = ["context", "tfidf", "semantic"]

    # Precompute TF-IDF on benchmark descriptions only (no app dataset).
    tfidf_vec, tfidf_mat, found_clean = None, None, None
    if "tfidf" in methods:
        found_clean = found_df["description"].apply(clean_text).tolist()
        tfidf_vec = TfidfVectorizer()
        try:
            tfidf_mat = tfidf_vec.fit_transform(
                found_clean + lost_df["description"].apply(clean_text).tolist())
        except ValueError:
            print("WARNING: empty TF-IDF vocabulary; tfidf scores will be 0.")
            tfidf_mat = None

    def tfidf_scores(lost, found):
        if tfidf_mat is None:
            return [0.0] * len(found)
        q = tfidf_vec.transform([clean_text(lost.get("description", ""))])
        base = tfidf_mat[:len(found)]
        return cosine_similarity(q, base).flatten().tolist()

    # Lazy Sentence-BERT load (only when requested).
    st_model, st_found_emb = None, None
    if "semantic" in methods:
        try:
            from sentence_transformers import SentenceTransformer
            print("Loading Sentence-BERT (all-MiniLM-L6-v2)...", flush=True)
            st_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            st_found_emb = st_model.encode(found_df["description"].astype(str).tolist(),
                                           normalize_embeddings=True,
                                           show_progress_bar=False)
        except Exception as e:  # noqa: BLE001 - report and continue with other methods
            print(f"WARNING: semantic method unavailable ({e}); skipping.")
            methods = [m for m in methods if m != "semantic"]

    def semantic_scores(lost, found):
        sims = cosine_similarity(
            st_model.encode([str(lost.get("description", ""))],
                            normalize_embeddings=True), st_found_emb).flatten()
        return sims.tolist()

    def zero_scores(lost, found):
        return [0.0] * len(found)

    scorers = {"context": zero_scores, "tfidf": tfidf_scores, "semantic": semantic_scores}

    results = []
    for m in methods:
        results.append(evaluate_method(lost_df, found_df, labels, scorers[m],
                                       m, args.top_n, args.threshold))

    print(f"\nQueries: {len(labels)} labels | {len(lost_df)} lost x {len(found_df)} found "
          f"| top_n={args.top_n}"
          + (f" | threshold={args.threshold}" if args.threshold is not None else ""))
    header = f"{'method':<12}{'Top-1':>8}{'Top-3':>8}{'Top-5':>8}{'MRR':>8}{'nDCG':>8}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(f"{r['method']:<12}{r['top1'] * 100:>7.2f}%{r['top3'] * 100:>7.2f}%"
              f"{r['top5'] * 100:>7.2f}%{r['mrr'] * 100:>7.2f}%{r['ndcg'] * 100:>7.2f}%")
        if r["abstain_acc"] is not None:
            print(f"  no-match abstention: {r['abstain_acc'] * 100:.1f}% "
                  f"({r['n_no_match']} no-match queries)")
    print("\nPer-query (first method shown):")
    for d in results[0]["details"]:
        print(f"  {d['lost_id']} -> top={d['top1']} expected={d['expected']} "
              f"rank={d['rank']} score={d['top_score']:.3f}")

    if args.output:
        out = []
        for r in results:
            for d in r["details"]:
                out.append({"method": r["method"], **d})
        pd.DataFrame(out).to_csv(args.output, index=False)
        print(f"\nDetails saved to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
