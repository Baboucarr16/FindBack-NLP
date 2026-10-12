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


    # --------------------------------------------------------
    # Check dataset
    # --------------------------------------------------------

    if df.empty:

        return pd.DataFrame()


    if embeddings is None:

        return pd.DataFrame()


    # --------------------------------------------------------
    # Convert lost description to embedding
    # --------------------------------------------------------

    lost_description = str(
        lost_report.get(
            "description",
            ""
        )
    )


    lost_embedding = _get_model().encode(
        [lost_description],
        normalize_embeddings=True
    )


    # --------------------------------------------------------
    # Calculate semantic similarity
    # --------------------------------------------------------

    semantic_scores = cosine_similarity(
        lost_embedding,
        embeddings
    ).flatten()


    results = []


    # --------------------------------------------------------
    # Compare against FOUND reports
    # --------------------------------------------------------

    for index, report in df.iterrows():

        report_type = str(
            report.get(
                "report_type",
                ""
            )
        ).strip().lower()


        # ----------------------------------------------------
        # Only compare against FOUND reports
        # ----------------------------------------------------

        if report_type != "found":

            continue


        # ----------------------------------------------------
        # Semantic similarity
        # ----------------------------------------------------

        semantic_score = float(
            semantic_scores[index]
        )


        # ----------------------------------------------------
        # Location similarity
        # ----------------------------------------------------

        location_score = (
            calculate_location_similarity(
                lost_report,
                report
            )
        )


        # ----------------------------------------------------
        # Time similarity
        # ----------------------------------------------------

        time_score = (
            calculate_time_similarity(
                lost_report,
                report
            )
        )


        # ----------------------------------------------------
        # Category similarity
        # ----------------------------------------------------

        category_score = (
            calculate_category_similarity(
                lost_report,
                report
            )
        )


        # ----------------------------------------------------
        # FINAL MATCH SCORE
        #
        # Semantic     = 50%
        # Location     = 25%
        # Time         = 15%
        # Category     = 10%
        # ----------------------------------------------------

        final_score = (

            semantic_score * 0.50

            + location_score * 0.25

            + time_score * 0.15

            + category_score * 0.10
        )


        # ----------------------------------------------------
        # Save result
        # ----------------------------------------------------

        results.append({

            "report_id":
                report.get(
                    "report_id",
                    ""
                ),

            "item_category":
                report.get(
                    "item_category",
                    ""
                ),

            "description":
                report.get(
                    "description",
                    ""
                ),

            "organization_type":
                report.get(
                    "organization_type",
                    ""
                ),

            "organization_name":
                report.get(
                    "organization_name",
                    ""
                ),

            "campus_or_branch":
                report.get(
                    "campus_or_branch",
                    ""
                ),

            "building_or_terminal":
                report.get(
                    "building_or_terminal",
                    ""
                ),

            "floor_or_level":
                report.get(
                    "floor_or_level",
                    ""
                ),

            "specific_area":
                report.get(
                    "specific_area",
                    ""
                ),

            "date":
                report.get(
                    "date",
                    ""
                ),

            "approx_time":
                report.get(
                    "approx_time",
                    ""
                ),

            "semantic_score":
                semantic_score,

            "location_score":
                location_score,

            "time_score":
                time_score,

            "category_score":
                category_score,

            "final_score":
                final_score
        })


    # --------------------------------------------------------
    # Convert results to DataFrame
    # --------------------------------------------------------

    results_df = pd.DataFrame(
        results
    )


    if results_df.empty:

        return results_df


    # --------------------------------------------------------
    # Sort by final score
    # --------------------------------------------------------

    results_df = results_df.sort_values(
        by="final_score",
        ascending=False
    )


    # --------------------------------------------------------
    # Return top matches
    # --------------------------------------------------------

    return results_df.head(
        top_n
    )


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