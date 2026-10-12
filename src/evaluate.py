import pandas as pd

from matcher import find_matches


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
# EVALUATION VARIABLES
# ============================================================

results = []

correct_top_1 = 0
correct_top_3 = 0


# ============================================================
# START EVALUATION
# ============================================================

print("\n")
print("=" * 70)
print("                 FINDBACK EVALUATION")
print("=" * 70)

print(
    f"\nTesting {len(known_matches)} known Lost -> Found pairs..."
)


# ============================================================
# TEST EACH LOST REPORT
# ============================================================

for lost_id, correct_found_id in known_matches.items():

    print("\n" + "-" * 70)

    print(
        f"Lost Report: {lost_id}"
    )

    print(
        f"Expected Match: {correct_found_id}"
    )

    # Get top 5 matches
    matches = find_matches(
        lost_id,
        top_n=5
    )

    # Make sure results exist
    if matches.empty:

        print("No matches returned.")

        results.append({

            "lost_report": lost_id,
            "expected_match": correct_found_id,
            "top_match": "None",
            "correct_rank": "Not Found",
            "correct_score": 0,
            "top_1_correct": False,
            "top_3_correct": False

        })

        continue

    # List of ranked report IDs
    ranked_ids = matches[
        "report_id"
    ].tolist()


    # ========================================================
    # TOP 1
    # ========================================================

    top_1 = ranked_ids[0]

    top_1_correct = (
        top_1 == correct_found_id
    )

    if top_1_correct:
        correct_top_1 += 1


    # ========================================================
    # TOP 3
    # ========================================================

    top_3_correct = (
        correct_found_id
        in ranked_ids[:3]
    )

    if top_3_correct:
        correct_top_3 += 1


    # ========================================================
    # CORRECT MATCH RANK
    # ========================================================

    if correct_found_id in ranked_ids:

        rank = (
            ranked_ids.index(
                correct_found_id
            ) + 1
        )

        correct_score = matches.loc[
            matches["report_id"]
            == correct_found_id,
            "final_score"
        ].iloc[0]

    else:

        rank = "Not in Top 5"

        correct_score = 0


    # ========================================================
    # DISPLAY RESULT
    # ========================================================

    print(
        f"Top Match: {top_1}"
    )

    print(
        f"Correct Match Rank: {rank}"
    )

    print(
        f"Correct Match Score: "
        f"{correct_score * 100:.2f}%"
    )

    print(
        f"Top-1 Correct: "
        f"{'YES' if top_1_correct else 'NO'}"
    )

    print(
        f"Top-3 Correct: "
        f"{'YES' if top_3_correct else 'NO'}"
    )


    # ========================================================
    # STORE RESULT
    # ========================================================

    results.append({

        "lost_report": lost_id,

        "expected_match": correct_found_id,

        "top_match": top_1,

        "correct_rank": rank,

        "correct_score": correct_score,

        "top_1_correct": top_1_correct,

        "top_3_correct": top_3_correct

    })


# ============================================================
# CALCULATE FINAL METRICS
# ============================================================

total_tests = len(known_matches)


top_1_accuracy = (
    correct_top_1 / total_tests
)


top_3_accuracy = (
    correct_top_3 / total_tests
)


# ============================================================
# FINAL RESULTS
# ============================================================

print("\n")
print("=" * 70)
print("                    FINAL RESULTS")
print("=" * 70)

print(
    f"\nTotal Test Cases: "
    f"{total_tests}"
)

print(
    f"\nTop-1 Accuracy: "
    f"{top_1_accuracy * 100:.2f}%"
)

print(
    f"Top-3 Accuracy: "
    f"{top_3_accuracy * 100:.2f}%"
)


# ============================================================
# SAVE RESULTS
# ============================================================

results_df = pd.DataFrame(results)


results_df.to_csv(
    "dataset/evaluation_results.csv",
    index=False
)


print(
    "\nEvaluation results saved to:"
)

print(
    "dataset/evaluation_results.csv"
)

print("\n" + "=" * 70)