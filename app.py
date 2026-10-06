import sys
import os
import csv

from flask import Flask, render_template, request


# ============================================================
# PROJECT PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

SRC_DIR = os.path.join(
    BASE_DIR,
    "src"
)

DATASET_DIR = os.path.join(
    BASE_DIR,
    "dataset"
)

DATASET_FILE = os.path.join(
    DATASET_DIR,
    "findback_reports.csv"
)


# Allow Python to import files from src/
sys.path.insert(0, SRC_DIR)


# ============================================================
# IMPORT FINDBACK NLP ENGINE
# ============================================================

from semantic_matcher import (
    find_semantic_matches_for_report
)


# ============================================================
# CREATE FLASK APPLICATION
# ============================================================

app = Flask(__name__)


# ============================================================
# HELPER: GENERATE NEXT REPORT ID
# ============================================================

def generate_report_id():

    existing_ids = []

    try:

        with open(
            DATASET_FILE,
            "r",
            encoding="utf-8",
            newline=""
        ) as file:

            reader = csv.DictReader(file)

            for row in reader:

                report_id = str(
                    row.get("report_id", "")
                ).strip()

                if report_id.startswith("FB"):

                    try:

                        number = int(
                            report_id[2:]
                        )

                        existing_ids.append(
                            number
                        )

                    except ValueError:

                        pass

    except FileNotFoundError:

        pass


    if not existing_ids:

        next_number = 1

    else:

        next_number = max(
            existing_ids
        ) + 1


    return f"FB{next_number:03d}"


# ============================================================
# HELPER: SAVE FOUND REPORT
# ============================================================

def save_found_report(found_report):

    fieldnames = [
        "report_id",
        "report_type",
        "item_category",
        "description",
        "organization_type",
        "organization_name",
        "campus_or_branch",
        "building_or_terminal",
        "floor_or_level",
        "specific_area",
        "date",
        "approx_time",
        "status"
    ]


    file_exists = os.path.exists(
        DATASET_FILE
    )


    os.makedirs(
        DATASET_DIR,
        exist_ok=True
    )


    with open(
        DATASET_FILE,
        "a",
        encoding="utf-8",
        newline=""
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )


        if not file_exists:

            writer.writeheader()


        writer.writerow(
            found_report
        )


# ============================================================
# HELPER: CHECK LOCATION INPUT
# ============================================================

def validate_location_input(
    description,
    organization_name
):

    description_lower = (
        description
        .strip()
        .lower()
    )

    organization_lower = (
        organization_name
        .strip()
        .lower()
    )


    # Exact duplicate
    if description_lower == organization_lower:

        return (
            "Please enter the actual place/organization "
            "in the Place / Organization field. "
            "For example: Greenfield University."
        )


    # Common accidental input
    suspicious_phrases = [
        "i lost ",
        "i lost my ",
        "lost my ",
        "i found ",
        "i found my ",
        "was found ",
        "is lost "
    ]


    for phrase in suspicious_phrases:

        if organization_lower.startswith(
            phrase
        ):

            return (
                "The Place / Organization field "
                "appears to contain your item description. "
                "Please enter a place such as "
                "Greenfield University, Metro International Airport, "
                "or Central Mall."
            )


    return None


# ============================================================
# HOME PAGE
# ============================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# ============================================================
# SEARCH FOR LOST ITEM MATCHES
# ============================================================

@app.route(
    "/search",
    methods=["POST"]
)
def search():

    # --------------------------------------------------------
    # Get user input
    # --------------------------------------------------------

    item_category = request.form.get(
        "item_category",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    organization_type = request.form.get(
        "organization_type",
        ""
    ).strip()

    organization_name = request.form.get(
        "organization_name",
        ""
    ).strip()

    campus_or_branch = request.form.get(
        "campus_or_branch",
        ""
    ).strip()

    building_or_terminal = request.form.get(
        "building_or_terminal",
        ""
    ).strip()

    floor_or_level = request.form.get(
        "floor_or_level",
        ""
    ).strip()

    specific_area = request.form.get(
        "specific_area",
        ""
    ).strip()

    date = request.form.get(
        "date",
        ""
    ).strip()

    approx_time = request.form.get(
        "approx_time",
        ""
    ).strip()


    # --------------------------------------------------------
    # Validate basic input
    # --------------------------------------------------------

    if not item_category:

        return render_template(
            "index.html",
            error="Please select an item category."
        )


    if not description:

        return render_template(
            "index.html",
            error="Please describe the item you lost."
        )


    if not organization_name:

        return render_template(
            "index.html",
            error="Please enter the place where you lost the item."
        )


    if not date:

        return render_template(
            "index.html",
            error="Please enter the date."
        )


    if not approx_time:

        return render_template(
            "index.html",
            error="Please enter the approximate time."
        )


    # --------------------------------------------------------
    # Validate location data
    # --------------------------------------------------------

    location_error = validate_location_input(
        description,
        organization_name
    )


    if location_error:

        return render_template(
            "index.html",
            error=location_error
        )


    # --------------------------------------------------------
    # Create lost report
    # --------------------------------------------------------

    lost_report = {

        "report_id":
            "USER_REPORT",

        "report_type":
            "Lost",

        "item_category":
            item_category,

        "description":
            description,

        "organization_type":
            organization_type,

        "organization_name":
            organization_name,

        "campus_or_branch":
            campus_or_branch,

        "building_or_terminal":
            building_or_terminal,

        "floor_or_level":
            floor_or_level,

        "specific_area":
            specific_area,

        "date":
            date,

        "approx_time":
            approx_time,

        "status":
            "Lost"
    }


    # --------------------------------------------------------
    # Run Sentence-BERT matching
    # --------------------------------------------------------

    matches = find_semantic_matches_for_report(
        lost_report,
        top_n=5
    )


    # --------------------------------------------------------
    # Convert results for HTML
    # --------------------------------------------------------

    if matches.empty:

        match_records = []

    else:

        match_records = matches.to_dict(
            orient="records"
        )


    # --------------------------------------------------------
    # Display results
    # --------------------------------------------------------

    return render_template(
        "results.html",
        matches=match_records,
        lost_report=lost_report
    )


# ============================================================
# REPORT A FOUND ITEM
# ============================================================

@app.route(
    "/found",
    methods=["GET", "POST"]
)
def found():

    # --------------------------------------------------------
    # Display found-item form
    # --------------------------------------------------------

    if request.method == "GET":

        return render_template(
            "found.html"
        )


    # --------------------------------------------------------
    # Get found-item input
    # --------------------------------------------------------

    item_category = request.form.get(
        "item_category",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    organization_type = request.form.get(
        "organization_type",
        ""
    ).strip()

    organization_name = request.form.get(
        "organization_name",
        ""
    ).strip()

    campus_or_branch = request.form.get(
        "campus_or_branch",
        ""
    ).strip()

    building_or_terminal = request.form.get(
        "building_or_terminal",
        ""
    ).strip()

    floor_or_level = request.form.get(
        "floor_or_level",
        ""
    ).strip()

    specific_area = request.form.get(
        "specific_area",
        ""
    ).strip()

    date = request.form.get(
        "date",
        ""
    ).strip()

    approx_time = request.form.get(
        "approx_time",
        ""
    ).strip()


    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    if not item_category:

        return render_template(
            "found.html",
            error="Please select the item category."
        )


    if not description:

        return render_template(
            "found.html",
            error="Please describe the found item."
        )


    if not organization_name:

        return render_template(
            "found.html",
            error="Please enter where the item was found."
        )


    if not date:

        return render_template(
            "found.html",
            error="Please enter the date."
        )


    if not approx_time:

        return render_template(
            "found.html",
            error="Please enter the approximate time."
        )


    # --------------------------------------------------------
    # Generate ID
    # --------------------------------------------------------

    report_id = generate_report_id()


    # --------------------------------------------------------
    # Create found report
    # --------------------------------------------------------

    found_report = {

        "report_id":
            report_id,

        "report_type":
            "Found",

        "item_category":
            item_category,

        "description":
            description,

        "organization_type":
            organization_type,

        "organization_name":
            organization_name,

        "campus_or_branch":
            campus_or_branch,

        "building_or_terminal":
            building_or_terminal,

        "floor_or_level":
            floor_or_level,

        "specific_area":
            specific_area,

        "date":
            date,

        "approx_time":
            approx_time,

        "status":
            "Found"
    }


    # --------------------------------------------------------
    # Save report
    # --------------------------------------------------------

    save_found_report(
        found_report
    )


    # --------------------------------------------------------
    # Confirmation
    # --------------------------------------------------------

    return render_template(
        "found.html",
        success=True,
        report_id=report_id
    )


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    print("\n")

    print("=" * 60)

    print(
        "              FINDBACK APPLICATION"
    )

    print("=" * 60)

    print(
        "\nOpen your browser at:"
    )

    print(
        "http://127.0.0.1:5000"
    )

    print(
        "\nReport a found item at:"
    )

    print(
        "http://127.0.0.1:5000/found"
    )

    print(
        "\nPress CTRL+C to stop the server."
    )

    print("=" * 60)


    app.run(
        debug=True
    )