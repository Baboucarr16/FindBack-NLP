import os
import threading
import pandas as pd

from sklearn.metrics.pairwise import cosine_similarity

from matcher import (
    calculate_location_similarity,
    calculate_time_similarity,
    calculate_category_similarity
)


# ============================================================
# PROJECT PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

DATASET_FILE = os.path.join(
    BASE_DIR,
    "dataset",
    "findback_reports.csv"
)


# ============================================================
# GLOBAL DATA
# ============================================================

df = pd.DataFrame()

embeddings = None

dataset_modified_time = None

model = None
_model_lock = threading.Lock()
_dataset_lock = threading.Lock()


def _get_model():
    """Load Sentence-BERT once, on the first request that needs a match."""

    global model

    if model is None:
        with _model_lock:
            if model is None:
                from sentence_transformers import SentenceTransformer

                print("\nLoading Sentence-BERT model...")
                model = SentenceTransformer(
                    "sentence-transformers/all-MiniLM-L6-v2"
                )
                print("Model loaded successfully!")

    return model


# ============================================================
# LOAD / REFRESH DATASET
# ============================================================

def load_dataset():

    global df
    global embeddings
    global dataset_modified_time

    with _dataset_lock:
        # --------------------------------------------------------
        # Check whether dataset exists
        # --------------------------------------------------------

        if not os.path.exists(DATASET_FILE):

            print("\nERROR: Dataset file not found:")
            print(DATASET_FILE)
            df = pd.DataFrame()
            embeddings = None
            dataset_modified_time = None
            return

        # --------------------------------------------------------
        # Get file modification time and skip unchanged data
        # --------------------------------------------------------

        current_modified_time = os.path.getmtime(DATASET_FILE)
        if current_modified_time == dataset_modified_time:
            return

        # --------------------------------------------------------
        # Load and prepare the changed dataset
        # --------------------------------------------------------

        print("\n")
        print("=" * 60)
        print("REFRESHING FINDBACK DATASET")
        print("=" * 60)

        new_df = pd.read_csv(DATASET_FILE).reset_index(drop=True)
        new_df["description"] = (
            new_df["description"]
            .fillna("")
            .astype(str)
        )

        print(f"Dataset loaded: {len(new_df)} reports")

        # Encoding happens only when a match is requested, and the
        # resulting vectors are reused until the CSV changes.
        if len(new_df) > 0:
            new_embeddings = _get_model().encode(
                new_df["description"].tolist(),
                normalize_embeddings=True,
                show_progress_bar=True
            )
        else:
            new_embeddings = None

        df = new_df
        embeddings = new_embeddings
        dataset_modified_time = current_modified_time


# ============================================================
# MATCH A NEW LOST REPORT
# ============================================================

def find_semantic_matches_for_report(
    lost_report,
    top_n=5
):

    # --------------------------------------------------------
    # IMPORTANT:
    # Check whether the CSV has changed.
    #
    # This allows newly submitted found reports to become
    # searchable without restarting Flask.
    # --------------------------------------------------------

    load_dataset()


    if df.empty or embeddings is None:
        return pd.DataFrame()

    lost_embedding = _get_model().encode(
        [str(lost_report.get("description", "") or "")],
        normalize_embeddings=True
    )
    all_scores = cosine_similarity(lost_embedding, embeddings).flatten()
    found_reports = []
    found_scores = []
    for index, report in df.iterrows():
        if str(report.get("report_type", "")).strip().lower() != "found":
            continue
        found_reports.append(report.to_dict())
        found_scores.append(float(all_scores[index]))
    return find_semantic_matches_against_reports(
        lost_report, found_reports, top_n=top_n,
        _semantic_scores=found_scores
    )


def find_semantic_matches_against_reports(lost_report, found_reports,
                                          top_n=5, _semantic_scores=None):
    """Rank supplied Found rows with the existing scorer and weights.

    Used by the Supabase backend so its rows go through the same model
    and component scoring as CSV rows, without loading or mixing CSV data.
    """
    found_reports = [
        dict(row) for row in (found_reports or [])
        if str(row.get("report_type", "")).strip().lower() == "found"
    ]
    if not found_reports:
        return pd.DataFrame()

    if _semantic_scores is None:
        descriptions = [str(row.get("description", "") or "")
                        for row in found_reports]
        encoded = _get_model().encode(
            [str(lost_report.get("description", "") or ""), *descriptions],
            normalize_embeddings=True
        )
        semantic_scores = cosine_similarity(
            encoded[:1], encoded[1:]).flatten()
    else:
        semantic_scores = _semantic_scores

    results = []
    for report, semantic_score in zip(found_reports, semantic_scores):
        scoring_report = dict(report)
        scoring_report["date"] = (report.get("date")
                                  or report.get("event_date") or "")
        lost_scoring_report = dict(lost_report)
        lost_scoring_report["date"] = (lost_report.get("date")
                                       or lost_report.get("event_date") or "")
        semantic_score = float(semantic_score)
        location_score = calculate_location_similarity(
            lost_scoring_report, scoring_report)
        time_score = calculate_time_similarity(
            lost_scoring_report, scoring_report)
        category_score = calculate_category_similarity(
            lost_scoring_report, scoring_report)
        results.append({
            "id": report.get("id", ""),
            "report_id": (report.get("legacy_report_id")
                          or report.get("report_id") or report.get("id", "")),
            "item_category": report.get("item_category", ""),
            "description": report.get("description", ""),
            "organization_type": report.get("organization_type", ""),
            "organization_name": report.get("organization_name", ""),
            "campus_or_branch": report.get("campus_or_branch", ""),
            "building_or_terminal": report.get("building_or_terminal", ""),
            "floor_or_level": report.get("floor_or_level", ""),
            "specific_area": report.get("specific_area", ""),
            "date": scoring_report["date"],
            "approx_time": report.get("approx_time", ""),
            "semantic_score": semantic_score,
            "location_score": location_score,
            "time_score": time_score,
            "category_score": category_score,
            "final_score": (semantic_score * 0.50 + location_score * 0.25
                            + time_score * 0.15 + category_score * 0.10),
        })
    return (pd.DataFrame(results).sort_values(
        by="final_score", ascending=False).head(top_n))


# ============================================================
# MATCH AN EXISTING REPORT
# ============================================================

def find_semantic_matches(
    lost_report_id,
    top_n=5
):

    # --------------------------------------------------------
    # Refresh dataset if necessary
    # --------------------------------------------------------

    load_dataset()

    if df.empty:

        return pd.DataFrame()


    # --------------------------------------------------------
    # Find lost report
    # --------------------------------------------------------

    lost_indices = df.index[
        df["report_id"].astype(str)
        == str(lost_report_id)
    ]


    if len(lost_indices) == 0:

        print(
            f"Error: Report {lost_report_id} "
            f"was not found."
        )

        return pd.DataFrame()


    # --------------------------------------------------------
    # Get report
    # --------------------------------------------------------

    lost_index = lost_indices[0]


    lost_report = (
        df.loc[lost_index]
        .to_dict()
    )


    # --------------------------------------------------------
    # Run matching
    # --------------------------------------------------------

    return find_semantic_matches_for_report(
        lost_report,
        top_n
    )


# ============================================================
# DISPLAY MATCHES
# ============================================================

def display_matches(
    lost_report_id,
    matches
):

    print("\n")

    print("=" * 70)

    print(
        "              FINDBACK SEMANTIC MATCHING"
    )

    print("=" * 70)


    print(
        f"\nLost Report: {lost_report_id}"
    )


    if matches.empty:

        print(
            "\nNo matches found."
        )

        return


    for rank, (_, row) in enumerate(
        matches.iterrows(),
        start=1
    ):

        print(
            "\n" + "-" * 70
        )


        print(
            f"MATCH #{rank}"
        )


        print(
            f"Report ID: "
            f"{row['report_id']}"
        )


        print(
            f"Item: "
            f"{row['item_category']}"
        )


        print(
            f"Description: "
            f"{row['description']}"
        )


        print(
            f"\nSemantic Similarity: "
            f"{row['semantic_score'] * 100:.2f}%"
        )


        print(
            f"Location Similarity: "
            f"{row['location_score'] * 100:.2f}%"
        )


        print(
            f"Time Proximity: "
            f"{row['time_score'] * 100:.2f}%"
        )


        print(
            f"Category Match: "
            f"{row['category_score'] * 100:.2f}%"
        )


        print(
            f"\nFINAL MATCH SCORE: "
            f"{row['final_score'] * 100:.2f}%"
        )


    print(
        "\n" + "=" * 70
    )


# ============================================================
# TEST MODE
# ============================================================

if __name__ == "__main__":

    lost_report_id = "FB020"


    matches = find_semantic_matches(
        lost_report_id,
        top_n=5
    )


    display_matches(
        lost_report_id,
        matches
    )
