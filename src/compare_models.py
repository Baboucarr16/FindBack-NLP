import pandas as pd

from matcher import find_matches
from semantic_matcher import find_semantic_matches
from artifact_paths import output_path


# ============================================================
# KNOWN CORRECT MATCHES
# ============================================================

known_matches = {

    # Original cases
    "FB001": "FB002",
    "FB003": "FB004",
    "FB005": "FB006",
    "FB007": "FB008",
    "FB009": "FB010",
    "FB011": "FB012",

    # Hard cases
    "FB013": "FB014",
    "FB016": "FB017",
    "FB018": "FB019",
    "FB020": "FB021",
    "FB022": "FB023",
    "FB024": "FB025"
}


# ============================================================
# RESULT STORAGE
# ============================================================

comparison_results = []


tfidf_top1_correct = 0
tfidf_top3_correct = 0

semantic_top1_correct = 0
semantic_top3_correct = 0


# ============================================================
# START COMPARISON
# ============================================================

print("\n")
print("=" * 75)
print("                 FINDBACK MODEL COMPARISON")
print("=" * 75)

print(
    f"\nTesting {len(known_matches)} Lost -> Found pairs."
)

print(
    "\nLoading both matching systems..."
)


# ============================================================
# TEST EACH REPORT
# ============================================================

for lost_id, expected_id in known_matches.items():

    print("\n" + "-" * 75)

    print(
        f"Lost Report: {lost_id}"
    )

    print(
        f"Expected Match: {expected_id}"
    )


    # ========================================================
    # TF-IDF MODEL
    # ========================================================

    tfidf_results = find_matches(
        lost_id,
        top_n=5
    )

    tfidf_ids = (
        tfidf_results["report_id"].tolist()
    )


    if len(tfidf_ids) > 0:

        tfidf_top1 = tfidf_ids[0]

    else:

        tfidf_top1 = "None"


    tfidf_top1_correct_case = (
        tfidf_top1 == expected_id
    )


    tfidf_top3_correct_case = (
        expected_id in tfidf_ids[:3]
    )


    if tfidf_top1_correct_case:
        tfidf_top1_correct += 1


    if tfidf_top3_correct_case:
        tfidf_top3_correct += 1


    if expected_id in tfidf_ids:

        tfidf_rank = (
            tfidf_ids.index(expected_id) + 1
        )

        tfidf_score = tfidf_results.loc[
            tfidf_results["report_id"] == expected_id,
            "final_score"
        ].iloc[0]

    else:

        tfidf_rank = "Not in Top 5"
        tfidf_score = 0


    # ========================================================
    # SENTENCE-BERT MODEL
    # ========================================================

    semantic_results = find_semantic_matches(
        lost_id,
        top_n=5
    )

    semantic_ids = (
        semantic_results["report_id"].tolist()
    )


    if len(semantic_ids) > 0:

        semantic_top1 = semantic_ids[0]

    else:

        semantic_top1 = "None"


    semantic_top1_correct_case = (
        semantic_top1 == expected_id
    )


    semantic_top3_correct_case = (
        expected_id in semantic_ids[:3]
    )


    if semantic_top1_correct_case:
        semantic_top1_correct += 1


    if semantic_top3_correct_case:
        semantic_top3_correct += 1


    if expected_id in semantic_ids:

        semantic_rank = (
            semantic_ids.index(expected_id) + 1
        )

        semantic_score = semantic_results.loc[
            semantic_results["report_id"] == expected_id,
            "final_score"
        ].iloc[0]

    else:

        semantic_rank = "Not in Top 5"
        semantic_score = 0


    # ========================================================
    # DISPLAY CASE RESULT
    # ========================================================

    print("\nTF-IDF:")

    print(
        f"  Top Match: {tfidf_top1}"
    )

    print(
        f"  Correct Match Rank: {tfidf_rank}"
    )

    print(
        f"  Correct Match Score: "
        f"{tfidf_score * 100:.2f}%"
    )

    print(
        f"  Top-1: "
        f"{'YES' if tfidf_top1_correct_case else 'NO'}"
    )

    print(
        f"  Top-3: "
        f"{'YES' if tfidf_top3_correct_case else 'NO'}"
    )


    print("\nSentence-BERT:")

    print(
        f"  Top Match: {semantic_top1}"
    )

    print(
        f"  Correct Match Rank: {semantic_rank}"
    )

    print(
        f"  Correct Match Score: "
        f"{semantic_score * 100:.2f}%"
    )

    print(
        f"  Top-1: "
        f"{'YES' if semantic_top1_correct_case else 'NO'}"
    )

    print(
        f"  Top-3: "
        f"{'YES' if semantic_top3_correct_case else 'NO'}"
    )


    # ========================================================
    # SAVE CASE RESULT
    # ========================================================

    comparison_results.append({

        "lost_report":
            lost_id,

        "expected_match":
            expected_id,

        "tfidf_top_match":
            tfidf_top1,

        "tfidf_correct_rank":
            tfidf_rank,

        "tfidf_correct_score":
            tfidf_score,

        "tfidf_top1_correct":
            tfidf_top1_correct_case,

        "tfidf_top3_correct":
            tfidf_top3_correct_case,

        "semantic_top_match":
            semantic_top1,

        "semantic_correct_rank":
            semantic_rank,

        "semantic_correct_score":
            semantic_score,

        "semantic_top1_correct":
            semantic_top1_correct_case,

        "semantic_top3_correct":
            semantic_top3_correct_case
    })


# ============================================================
# CALCULATE ACCURACY
# ============================================================

total_tests = len(known_matches)


tfidf_top1_accuracy = (
    tfidf_top1_correct / total_tests
)


tfidf_top3_accuracy = (
    tfidf_top3_correct / total_tests
)


semantic_top1_accuracy = (
    semantic_top1_correct / total_tests
)


semantic_top3_accuracy = (
    semantic_top3_correct / total_tests
)


# ============================================================
# CALCULATE IMPROVEMENT
# ============================================================

top1_improvement = (
    semantic_top1_accuracy
    - tfidf_top1_accuracy
)


top3_improvement = (
    semantic_top3_accuracy
    - tfidf_top3_accuracy
)


# ============================================================
# FINAL COMPARISON
# ============================================================

print("\n\n")
print("=" * 75)
print("                    FINAL COMPARISON")
print("=" * 75)


print("\n")

print(
    f"{'MODEL':<25}"
    f"{'TOP-1':>15}"
    f"{'TOP-3':>15}"
)

print("-" * 55)


print(
    f"{'TF-IDF + Context':<25}"
    f"{tfidf_top1_accuracy * 100:>14.2f}%"
    f"{tfidf_top3_accuracy * 100:>14.2f}%"
)


print(
    f"{'Sentence-BERT + Context':<25}"
    f"{semantic_top1_accuracy * 100:>14.2f}%"
    f"{semantic_top3_accuracy * 100:>14.2f}%"
)


print("\n" + "-" * 55)


print(
    f"Top-1 Improvement: "
    f"{top1_improvement * 100:+.2f} percentage points"
)


print(
    f"Top-3 Improvement: "
    f"{top3_improvement * 100:+.2f} percentage points"
)


# ============================================================
# SAVE COMPARISON RESULTS
# ============================================================

comparison_df = pd.DataFrame(
    comparison_results
)


output_file = output_path("model_comparison_results.csv")
output_file.parent.mkdir(parents=True, exist_ok=True)


comparison_df.to_csv(
    output_file,
    index=False
)


print("\n")
print(
    "Detailed comparison saved to:"
)

print(
    output_file
)


print("\n" + "=" * 75)
print(
    "                 COMPARISON COMPLETE"
)

print("=" * 75)
