"""Check for duplicate / near-duplicate leakage between dev and held-out test sets.

Read-only. Exits 0 when clean, 1 when leakage is found.

Usage:
    python src/check_leakage.py --dev-dir benchmark/dev --test-dir benchmark/heldout_test
    python src/check_leakage.py --dev-file dataset_a.csv --test-file dataset_b.csv
"""

import argparse
import os
import re
import sys

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def clean_text(text):
    text = str(text).lower().replace("-", " ")
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def norm(s):
    return re.sub(r"\s+", " ", str(s).strip().lower())


def load_reports(path_or_dir):
    """Load lost.csv+found.csv from a dir, or a single csv file."""
    if os.path.isdir(path_or_dir):
        frames = []
        for name in ("lost.csv", "found.csv"):
            p = os.path.join(path_or_dir, name)
            if os.path.exists(p):
                frames.append(pd.read_csv(p, dtype=str).fillna(""))
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
    else:
        df = pd.read_csv(path_or_dir, dtype=str).fillna("")
    # Skip format-validation placeholders.
    if "report_id" in df.columns:
        df = df[~df["report_id"].str.startswith("EXAMPLE-")]
    return df.reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser(description="Check dev/test leakage.")
    ap.add_argument("--dev-dir", default="benchmark/dev")
    ap.add_argument("--test-dir", default="benchmark/heldout_test")
    ap.add_argument("--dev-file", default=None)
    ap.add_argument("--test-file", default=None)
    ap.add_argument("--threshold", type=float, default=0.85,
                    help="TF-IDF cosine threshold for near-duplicate flag.")
    args = ap.parse_args()

    dev_src = args.dev_file or args.dev_dir
    test_src = args.test_file or args.test_dir

    if not os.path.exists(dev_src) or not os.path.exists(test_src):
        print(f"ERROR: missing input: {dev_src} / {test_src}")
        return 2

    dev = load_reports(dev_src)
    test = load_reports(test_src)

    if dev.empty or test.empty:
        print("No real reports to compare (only EXAMPLE placeholders). "
              "Nothing to check - add real data first.")
        return 0

    for col in ("report_id", "description"):
        if col not in dev.columns or col not in test.columns:
            print(f"ERROR: required column '{col}' missing.")
            return 2

    flags = []

    # 1. Exact duplicate report_ids across splits.
    dup_ids = set(dev["report_id"]) & set(test["report_id"])
    for rid in sorted(dup_ids):
        flags.append((rid, "?", "duplicate report_id across dev/test", 1.0))

    # 2. Normalized exact description duplicates.
    dev_text = {norm(d): rid for rid, d in
                zip(dev["report_id"], dev["description"])}
    for _, row in test.iterrows():
        key = norm(row["description"])
        if key and key in dev_text:
            flags.append((dev_text[key], row["report_id"],
                          "identical normalized description", 1.0))

    # 3. Near-duplicate TF-IDF cosine.
    dev_clean = dev["description"].apply(clean_text).tolist()
    test_clean = test["description"].apply(clean_text).tolist()
    try:
        vec = TfidfVectorizer()
        mat = vec.fit_transform(dev_clean + test_clean)
        dev_mat = mat[:len(dev_clean)]
        test_mat = mat[len(dev_clean):]
        sims = cosine_similarity(test_mat, dev_mat)
        for i, test_row in test.iterrows():
            for j, dev_row in dev.iterrows():
                s = float(sims[i, j])
                if s >= args.threshold and norm(test_row["description"]) != norm(dev_row["description"]):
                    flags.append((dev_row["report_id"], test_row["report_id"],
                                  f"near-duplicate description (cosine={s:.3f})", s))
    except ValueError:
        print("WARNING: empty vocabulary - descriptions may be blank.")

    # Deduplicate flags.
    seen = set()
    unique = []
    for f in flags:
        if f not in seen:
            seen.add(f)
            unique.append(f)

    if not unique:
        print(f"OK: no leakage found ({len(dev)} dev x {len(test)} test reports).")
        return 0

    print(f"LEAKAGE: {len(unique)} flagged pair(s) "
          f"({len(dev)} dev x {len(test)} test reports):")
    for a, b, reason, score in sorted(unique, key=lambda x: -x[3]):
        print(f"  dev={a} test={b} :: {reason}")
    print("\nResolve by replacing the test event (rewording is not enough).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
