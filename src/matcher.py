import os
import pandas as pd

from difflib import SequenceMatcher

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from preprocess import clean_text


# ============================================================
# DATASET PATH
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
# LOAD DATASET
# ============================================================

df = pd.read_csv(
    DATASET_FILE
)

df = df.reset_index(
    drop=True
)


# ============================================================
# TEXT PREPROCESSING
# ============================================================

df["description"] = (
    df["description"]
    .fillna("")
    .astype(str)
)

df["clean_description"] = (
    df["description"]
    .apply(clean_text)
)


# ============================================================
# TF-IDF MODEL
# ============================================================

vectorizer = TfidfVectorizer()

tfidf_matrix = vectorizer.fit_transform(
    df["clean_description"]
)


# ============================================================
# NORMALIZE TEXT
# ============================================================

def normalize_value(value):

    if pd.isna(value):
        return ""

    value = str(value).strip().lower()

    return value


# ============================================================
# LOCATION SIMILARITY
# ============================================================

def calculate_location_similarity(
    lost_report,
    found_report
):

    location_weights = {

        "organization_name": 0.30,

        "campus_or_branch": 0.15,

        "building_or_terminal": 0.20,

        "floor_or_level": 0.10,

        "specific_area": 0.25
    }


    total_weight = 0.0

    matched_weight = 0.0


    for field, weight in location_weights.items():

        lost_value = normalize_value(
            lost_report.get(field, "")
        )

        found_value = normalize_value(
            found_report.get(field, "")
        )


        # ----------------------------------------------------
        # If either side does not provide this information,
        # do not penalize the match.
        # ----------------------------------------------------

        if not lost_value or not found_value:

            continue


        total_weight += weight


        # ----------------------------------------------------
        # Exact match
        # ----------------------------------------------------

        if lost_value == found_value:

            matched_weight += weight

            continue


        # ----------------------------------------------------
        # One value contains the other
        # ----------------------------------------------------

        if (
            lost_value in found_value
            or
            found_value in lost_value
        ):

            matched_weight += (
                weight * 0.90
            )

            continue


        # ----------------------------------------------------
        # Similar wording
        # ----------------------------------------------------

        similarity = SequenceMatcher(
            None,
            lost_value,
            found_value
        ).ratio()


        if similarity >= 0.80:

            matched_weight += (
                weight * 0.75
            )

        elif similarity >= 0.60:

            matched_weight += (
                weight * 0.50
            )


    # --------------------------------------------------------
    # If no location information was supplied
    # --------------------------------------------------------

    if total_weight == 0:

        return 0.0


    return matched_weight / total_weight


# ============================================================
# TIME SIMILARITY
# ============================================================

def calculate_time_similarity(
    lost_report,
    found_report
):

    lost_date = normalize_value(
        lost_report.get("date", "")
    )

    lost_time = normalize_value(
        lost_report.get("approx_time", "")
    )

    found_date = normalize_value(
        found_report.get("date", "")
    )

    found_time = normalize_value(
        found_report.get("approx_time", "")
    )


    # --------------------------------------------------------
    # Missing values
    # --------------------------------------------------------

    if not lost_date or not lost_time:

        return 0.0


    if not found_date or not found_time:

        return 0.0


    try:

        lost_datetime = pd.to_datetime(
            lost_date + " " + lost_time
        )

        found_datetime = pd.to_datetime(
            found_date + " " + found_time
        )

    except Exception:

        return 0.0


    difference = abs(
        (
            found_datetime - lost_datetime
        ).total_seconds() / 60
    )


    # --------------------------------------------------------
    # Time scoring
    # --------------------------------------------------------

    if difference <= 30:

        return 1.0

    elif difference <= 60:

        return 0.8

    elif difference <= 120:

        return 0.5

    elif difference <= 360:

        return 0.25

    elif difference <= 1440:

        return 0.10

    else:

        return 0.0


# ============================================================
# CATEGORY SIMILARITY
# ============================================================

def calculate_category_similarity(
    lost_report,
    found_report
):

    lost_category = normalize_value(
        lost_report.get(
            "item_category",
            ""
        )
    )

    found_category = normalize_value(
        found_report.get(
            "item_category",
            ""
        )
    )


    if not lost_category or not found_category:

        return 0.0


    if lost_category == found_category:

        return 1.0


    return 0.0


# ============================================================
# DESCRIPTION-ONLY TF-IDF MATCHING
# ============================================================

def find_matches(
    lost_report_id,
    top_n=5
):

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


    lost_index = lost_indices[0]

    lost_report = df.loc[
        lost_index
    ]


    lost_vector = tfidf_matrix[
        lost_index
    ]


    description_scores = (
        cosine_similarity(
            lost_vector,
            tfidf_matrix
        ).flatten()
    )


    results = []


    # ========================================================
    # COMPARE AGAINST FOUND REPORTS
    # ========================================================

    for index, report in df.iterrows():

        report_type = normalize_value(
            report.get(
                "report_type",
                ""
            )
        )


        if report_type != "found":

            continue


        # ----------------------------------------------------
        # Description
        # ----------------------------------------------------

        description_score = float(
            description_scores[index]
        )


        # ----------------------------------------------------
        # Location
        # ----------------------------------------------------

        location_score = (
            calculate_location_similarity(
                lost_report,
                report
            )
        )


        # ----------------------------------------------------
        # Time
        # ----------------------------------------------------

        time_score = (
            calculate_time_similarity(
                lost_report,
                report
            )
        )


        # ----------------------------------------------------
        # Category
        # ----------------------------------------------------

        category_score = (
            calculate_category_similarity(
                lost_report,
                report
            )
        )


        # ====================================================
        # FINAL SCORE
        # ====================================================

        final_score = (

            description_score * 0.50

            + location_score * 0.25

            + time_score * 0.15

            + category_score * 0.10
        )


        results.append({

            "report_id":
                report["report_id"],

            "item_category":
                report["item_category"],

            "description":
                report["description"],

            "organization_type":
                report["organization_type"],

            "organization_name":
                report["organization_name"],

            "campus_or_branch":
                report["campus_or_branch"],

            "building_or_terminal":
                report["building_or_terminal"],

            "floor_or_level":
                report["floor_or_level"],

            "specific_area":
                report["specific_area"],

            "date":
                report["date"],

            "approx_time":
                report["approx_time"],

            "description_score":
                description_score,

            "location_score":
                location_score,

            "time_score":
                time_score,

            "category_score":
                category_score,

            "final_score":
                final_score
        })


    # ========================================================
    # RESULTS DATAFRAME
    # ========================================================

    results_df = pd.DataFrame(
        results
    )


    if results_df.empty:

        return results_df


    results_df = results_df.sort_values(
        by="final_score",
        ascending=False
    )


    return results_df.head(
        top_n
    )


# ============================================================
# DISPLAY RESULTS
# ============================================================

def display_matches(
    lost_report_id,
    matches
):

    print("\n")

    print("=" * 65)

    print(
        "                    FINDBACK"
    )

    print(
        "             INTELLIGENT MATCHING"
    )

    print("=" * 65)


    print(
        f"\nSearching matches for: "
        f"{lost_report_id}"
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
            "\n" + "-" * 65
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
            f"\nDescription Similarity: "
            f"{row['description_score'] * 100:.2f}%"
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
        "\n" + "=" * 65
    )


# ============================================================
# TEST MODE
# ============================================================

if __name__ == "__main__":

    lost_report_id = "FB001"


    matches = find_matches(
        lost_report_id,
        top_n=5
    )


    display_matches(
        lost_report_id,
        matches
    )