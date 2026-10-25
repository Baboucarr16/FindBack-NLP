import sys
import os
import csv
import hmac
import secrets
import uuid

from flask import Flask, redirect, render_template, request, url_for
from flask import abort, session


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

from auth import (
    current_user,
    ensure_profile,
    friendly_auth_error,
    get_user_client,
    is_enabled as auth_enabled,
    login_required,
    login_session,
    logout_session,
    sign_in,
    sign_up,
)


# ============================================================
# CREATE FLASK APPLICATION
# ============================================================

app = Flask(__name__)


# Secret key signs login sessions. The default keeps local CSV mode
# working; production must set FLASK_SECRET_KEY (see .env.example).
_configured_secret = os.environ.get("FLASK_SECRET_KEY", "")
if (os.environ.get("FLASK_DEBUG", "1") == "0"
        and (not _configured_secret
             or _configured_secret == "dev-only-insecure-key"
             or _configured_secret == "change-me-to-a-random-value")):
    raise RuntimeError(
        "FLASK_SECRET_KEY must be set to a private random value when "
        "FLASK_DEBUG=0."
    )
app.secret_key = _configured_secret or "dev-only-insecure-key"
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(
        os.environ.get("FLASK_COOKIE_SECURE")
        == "1" or (
            os.environ.get("FLASK_COOKIE_SECURE") is None
            and os.environ.get("FLASK_DEBUG", "1") != "1"
        )
    ),
)


@app.before_request
def protect_form_posts():
    """Require a session-bound CSRF token for state-changing forms."""
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    if app.config.get("TESTING"):
        return None
    expected = session.get("csrf_token")
    supplied = request.form.get("csrf_token", "")
    if not expected or not supplied or not hmac.compare_digest(
            str(expected), str(supplied)):
        abort(400)
    return None


@app.context_processor
def form_security_context():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return {"csrf_token": session["csrf_token"]}


@app.context_processor
def report_submission_context():
    return {"submission_key": str(uuid.uuid4())}


@app.context_processor
def demo_data_context():
    """Label the checked-in synthetic CSV used by the local demo."""
    return {
        "local_demo_mode": not supabase_requested() and not invalid_storage_mode()
    }


def using_supabase():
    """True when the persistent Supabase backend is selected and
    configured. Otherwise the app runs in local CSV mode."""

    return (
        os.environ.get(
            "FINDBACK_STORE",
            ""
        ).strip().lower() == "supabase"
        and auth_enabled()
    )


def supabase_requested():
    return os.environ.get("FINDBACK_STORE", "").strip().lower() == "supabase"


def invalid_storage_mode():
    mode = os.environ.get("FINDBACK_STORE", "csv").strip().lower() or "csv"
    return mode not in {"csv", "supabase"}


def request_submission_key():
    value = request.form.get("submission_key", "").strip()
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError):
        return str(uuid.uuid4())


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


@app.get("/healthz")
def healthz():
    """Lightweight liveness endpoint; it does not query external services."""
    return {"status": "ok"}, 200


# ============================================================
# SEARCH FOR LOST ITEM MATCHES
# ============================================================

@app.route(
    "/search",
    methods=["POST"]
)
def search():

    if invalid_storage_mode():
        return render_template(
            "index.html",
            error="Storage mode must be csv or supabase."
        )

    if supabase_requested() and not using_supabase():
        return render_template(
            "index.html",
            error="Supabase storage is selected but is not configured."
        )

    if using_supabase() and not current_user():
        return redirect(url_for("login"))

    submission_key = request_submission_key()

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

    supabase_store = None
    if using_supabase():
        try:
            from store import SupabaseStore

            supabase_store = SupabaseStore(get_user_client())
            saved = supabase_store.save_report(
                {
                    "report_type": "Lost",
                    "item_category": item_category,
                    "description": description,
                    "organization_type": organization_type,
                    "organization_name": organization_name,
                    "campus_or_branch": campus_or_branch,
                    "building_or_terminal": building_or_terminal,
                    "floor_or_level": floor_or_level,
                    "specific_area": specific_area,
                    "event_date": date,
                    "approx_time": approx_time,
                },
                owner_id=current_user()["id"],
                idempotency_key=submission_key,
            )
            saved_row = saved[0] if isinstance(saved, list) else saved
            lost_report.update(saved_row)
            lost_report["date"] = saved_row.get("event_date") or date
            found_reports = supabase_store.list_found()
            from semantic_matcher import find_semantic_matches_against_reports

            matches = find_semantic_matches_against_reports(
                lost_report, found_reports, top_n=5
            )
        except Exception:
            return render_template(
                "index.html",
                error="Could not save or search reports. Please try again.",
                submission_key=submission_key
            )
    else:
        matches = find_semantic_matches_for_report(
            lost_report,
            top_n=5
        )


    # --------------------------------------------------------
    # Optional weak-match filter.
    #
    # FINDBACK_MIN_SCORE is unset by default, which preserves
    # the existing behavior (show all candidates).
    # When set (0.0 - 1.0), candidates below the cutoff are
    # hidden instead of being shown as matches.
    # The cutoff is untuned: choose it using real, labeled
    # development data, never the held-out test set.
    # --------------------------------------------------------

    min_score_raw = os.environ.get(
        "FINDBACK_MIN_SCORE",
        ""
    ).strip()

    min_score = None

    total_candidates = 0


    if not matches.empty:

        total_candidates = len(
            matches
        )

        if min_score_raw:

            try:

                min_score = float(
                    min_score_raw
                )

                matches = matches[
                    matches["final_score"]
                    >= min_score
                ]

            except ValueError:

                min_score = None


    # --------------------------------------------------------
    # Convert results for HTML, attaching one explanation
    # per candidate (component evidence only, no new scoring).
    # --------------------------------------------------------

    if matches.empty:

        match_records = []

    else:

        from explain import explain_match

        match_records = matches.to_dict(
            orient="records"
        )

        for record in match_records:

            record["explanation"] = explain_match(
                lost_report,
                record
            )

        if supabase_store is not None:
            try:
                from notify import get_notifier

                notifier = get_notifier()
                for record in match_records:
                    if not record.get("id"):
                        continue
                    supabase_store.upsert_match_result({
                        "lost_report_id": lost_report["id"],
                        "found_report_id": record["id"],
                        "semantic_score": record["semantic_score"],
                        "location_score": record["location_score"],
                        "time_score": record["time_score"],
                        "category_score": record["category_score"],
                        "final_score": record["final_score"],
                    })
                    if notifier:
                        try:
                            notifier(lost_report, record,
                                     record["final_score"])
                        except Exception:
                            pass
            except Exception:
                return render_template(
                    "index.html",
                    error="Could not save match results. Please try again.",
                    submission_key=submission_key
                )


    # --------------------------------------------------------
    # Display results
    # --------------------------------------------------------

    return render_template(
        "results.html",
        matches=match_records,
        lost_report=lost_report,
        min_score=min_score,
        total_candidates=total_candidates
    )


# ============================================================
# REPORT A FOUND ITEM
# ============================================================

@app.route(
    "/found",
    methods=["GET", "POST"]
)
def found():

    if invalid_storage_mode():
        return render_template(
            "found.html",
            error="Storage mode must be csv or supabase."
        )

    if supabase_requested() and not using_supabase():
        return render_template(
            "found.html",
            error="Supabase storage is selected but is not configured."
        )

    submission_key = request_submission_key() if request.method == "POST" else ""

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
    # Supabase mode: authenticated, owner-bound persistent save
    # followed by best-effort automatic matching. CSV mode below
    # is unchanged.
    # --------------------------------------------------------

    if using_supabase():

        user = current_user()

        if not user:

            return redirect(
                url_for("login")
            )


        try:

            from store import SupabaseStore

            user_store = SupabaseStore(
                get_user_client()
            )

            saved = user_store.save_report(
                {
                    "report_type": "Found",
                    "item_category": item_category,
                    "description": description,
                    "organization_type": organization_type,
                    "organization_name": organization_name,
                    "campus_or_branch": campus_or_branch,
                    "building_or_terminal": building_or_terminal,
                    "floor_or_level": floor_or_level,
                    "specific_area": specific_area,
                    "event_date": date or None,
                    "approx_time": approx_time or None,
                },
                owner_id=user["id"],
                idempotency_key=submission_key
            )

        except Exception:

            return render_template(
                "found.html",
                error=(
                    "Could not save your report. Please try again."
                ),
                submission_key=submission_key
            )


        # ----------------------------------------------------
        # Best-effort automatic matching (never blocks success).
        #
        # Pairs persist through the saver's own rights; notifications
        # go through the server-side service-role writer so inbox RLS
        # stays least-privilege. Without a service key, notifying is
        # skipped and counted, never failed loudly.
        # --------------------------------------------------------

        try:

            from auto_match import process_new_found_report
            from notify import get_notifier

            process_new_found_report(
                saved[0] if isinstance(saved, list) else saved,
                user_store,
                notify_fn=get_notifier()
            )

        except Exception:

            pass


        saved_row = saved[0] if isinstance(saved, list) else saved

        return render_template(
            "found.html",
            success=True,
            report_id=str(saved_row.get("id", ""))[:8]
        )


    # --------------------------------------------------------
    # Generate ID and save report.
    #
    # A failed read or write must not display a false success,
    # so any filesystem error returns the form with an error
    # message instead of a confirmation.
    # --------------------------------------------------------

    try:

        report_id = generate_report_id()


        # ----------------------------------------------------
        # Create found report
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # Save report
        # --------------------------------------------------------

        save_found_report(
            found_report
        )

    except OSError:

        return render_template(
            "found.html",
            error=(
                "Could not save your report. Please try again."
            )
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
# REGISTER
# ============================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if current_user():

        return redirect(
            url_for("home")
        )


    if request.method == "GET":

        return render_template(
            "register.html",
            auth_enabled=auth_enabled()
        )


    email = request.form.get(
        "email",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )


    if not email or "@" not in email:

        return render_template(
            "register.html",
            auth_enabled=auth_enabled(),
            error="Please enter a valid email address."
        )


    if len(password) < 6:

        return render_template(
            "register.html",
            auth_enabled=auth_enabled(),
            error="Password must be at least 6 characters."
        )


    try:

        user = sign_up(
            email,
            password
        )

    except RuntimeError:

        return render_template(
            "register.html",
            auth_enabled=auth_enabled(),
            error="Authentication is not available. Please check server configuration."
        )

    except Exception as exc:

        return render_template(
            "register.html",
            auth_enabled=auth_enabled(),
            error=friendly_auth_error(exc)
        )


    # --------------------------------------------------------
    # Email confirmation required: no session exists yet, so
    # the account must NOT be logged in here.
    # --------------------------------------------------------

    if not user.get("confirmed"):

        return render_template(
            "register.html",
            auth_enabled=auth_enabled(),
            message=(
                "Account created. Please check your inbox "
                "for the confirmation link, then log in."
            )
        )


    try:
        ensure_profile(
            get_user_client(user),
            user["id"],
            user.get("email", "")
        )
    except Exception:
        return render_template(
            "register.html", auth_enabled=auth_enabled(),
            error="Could not finish setting up your account. Please log in and try again."
        )

    login_session(user)


    return redirect(
        url_for("home")
    )


# ============================================================
# LOGIN / LOGOUT
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if current_user():

        return redirect(
            url_for("home")
        )


    if request.method == "GET":

        return render_template(
            "login.html",
            auth_enabled=auth_enabled()
        )


    email = request.form.get(
        "email",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )


    if not email or not password:

        return render_template(
            "login.html",
            auth_enabled=auth_enabled(),
            error="Please enter your email and password."
        )


    try:

        user = sign_in(
            email,
            password
        )

    except RuntimeError:

        return render_template(
            "login.html",
            auth_enabled=auth_enabled(),
            error="Authentication is not available. Please check server configuration."
        )

    except Exception as exc:

        return render_template(
            "login.html",
            auth_enabled=auth_enabled(),
            error=friendly_auth_error(exc)
        )


    try:
        ensure_profile(
            get_user_client(user),
            user["id"],
            user.get("email", "")
        )
    except Exception:
        return render_template(
            "login.html", auth_enabled=auth_enabled(),
            error="Could not finish setting up your account. Please try again."
        )

    login_session(user)


    return redirect(
        url_for("home")
    )


@app.route("/logout", methods=["POST"])
def logout():

    logout_session()

    return redirect(
        url_for("home")
    )


# ============================================================
# CLAIMS (Supabase mode only; private by design)
# ============================================================

def _claims_store_or_error():
    """Return (store, user, error_response) for claim routes."""

    if not using_supabase():

        return (
            None,
            None,
            render_template(
                "claims.html",
                my_claims=[],
                incoming_claims=[],
                error=(
                    "Claims need Supabase configuration. "
                    "The app is running in local CSV mode."
                )
            )
        )

    from store import SupabaseStore

    try:

        user_store = SupabaseStore(
            get_user_client()
        )

    except Exception:

        return (
            None,
            None,
            render_template(
                "claims.html",
                my_claims=[],
                incoming_claims=[],
                error="Could not reach the database. Please try again."
            )
        )

    return user_store, current_user(), None


@app.route("/claims")
@login_required
def claims():

    user_store, user, error_response = _claims_store_or_error()

    if error_response is not None:

        return error_response


    try:

        my_claims = user_store.list_my_claims(
            user["id"]
        )

        incoming_claims = user_store.list_claims_on_my_reports(
            user["id"]
        )

    except Exception:

        return render_template(
            "claims.html",
            my_claims=[],
            incoming_claims=[],
            error="Could not load claims. Please try again."
        )


    return render_template(
        "claims.html",
        my_claims=my_claims,
        incoming_claims=incoming_claims
    )


@app.route(
    "/claims/new",
    methods=["GET", "POST"]
)
@login_required
def claim_new():

    user_store, user, error_response = _claims_store_or_error()

    if error_response is not None:

        return error_response


    if request.method == "GET":

        report_id = request.args.get(
            "report_id",
            ""
        ).strip()

        report = user_store.get_report(
            report_id
        ) if report_id else None

        if report is None:

            return render_template(
                "claim_form.html",
                report=None,
                error="Found report not found or not visible to you."
            )

        if report.get("report_type") != "Found":

            return render_template(
                "claim_form.html",
                report=report,
                error="Only found-item reports can be claimed."
            )

        if report.get("owner_id") == user["id"]:

            return render_template(
                "claim_form.html",
                report=report,
                error="You cannot claim your own report."
            )

        return render_template(
            "claim_form.html",
            report=report
        )


    report_id = request.form.get(
        "report_id",
        ""
    ).strip()

    note = request.form.get(
        "claim_note",
        ""
    ).strip()[:2000]


    report = user_store.get_report(
        report_id
    )

    if report is None or report.get("report_type") != "Found":

        return render_template(
            "claim_form.html",
            report=report,
            error="Found report not found or not visible to you."
        )

    if report.get("owner_id") == user["id"]:

        return render_template(
            "claim_form.html",
            report=report,
            error="You cannot claim your own report."
        )


    try:

        user_store.create_claim(
            report_id,
            user["id"],
            note
        )

    except ValueError:

        return render_template(
            "claim_form.html",
            report=report,
            error="You have already filed a claim for this report."
        )

    except Exception:

        return render_template(
            "claim_form.html",
            report=report,
            error="Could not file the claim. Please try again."
        )


    return redirect(
        url_for("claims")
    )


@app.route(
    "/claims/<claim_id>/decision",
    methods=["POST"]
)
@login_required
def claim_decision(claim_id):

    user_store, user, error_response = _claims_store_or_error()

    if error_response is not None:

        return error_response


    action = request.form.get(
        "action",
        ""
    ).strip()

    if action not in ("approve", "reject"):

        return redirect(
            url_for("claims")
        )


    try:

        user_store.decide_claim(
            claim_id,
            action == "approve",
            user["id"]
        )

    except PermissionError:

        return render_template(
            "claims.html",
            my_claims=[],
            incoming_claims=[],
            error="Only the report owner can decide this claim."
        )

    except ValueError:

        return render_template(
            "claims.html",
            my_claims=[],
            incoming_claims=[],
            error="The claim was not found or is no longer pending."
        )

    except Exception:

        return render_template(
            "claims.html",
            my_claims=[],
            incoming_claims=[],
            error="Could not decide the claim. Please try again."
        )


    return redirect(
        url_for("claims")
    )


# ============================================================
# NOTIFICATIONS INBOX (Supabase mode, owner-only)
# ============================================================

@app.route("/notifications")
@login_required
def notifications():

    if not using_supabase():

        return render_template(
            "notifications.html",
            notifications=[],
            error=(
                "Notifications need Supabase configuration. "
                "The app is running in local CSV mode."
            )
        )

    from store import SupabaseStore

    try:

        user_store = SupabaseStore(
            get_user_client()
        )

        notes = user_store.list_notifications(
            current_user()["id"]
        )

    except Exception:

        return render_template(
            "notifications.html",
            notifications=[],
            error="Could not load notifications. Please try again."
        )


    return render_template(
        "notifications.html",
        notifications=notes
    )


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # Server configuration.
    #
    # Local default preserves existing behavior (debug on).
    # Production deployments must set FLASK_DEBUG=0 and use
    # the platform-provided PORT (see Procfile / wsgi.py).
    # --------------------------------------------------------

    host = os.environ.get(
        "HOST",
        "127.0.0.1"
    )

    port = int(
        os.environ.get(
            "PORT",
            "5000"
        )
    )

    debug = (
        os.environ.get(
            "FLASK_DEBUG",
            "1"
        ) == "1"
    )

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
        f"http://{host}:{port}"
    )

    print(
        "\nReport a found item at:"
    )

    print(
        f"http://{host}:{port}/found"
    )

    print(
        "\nPress CTRL+C to stop the server."
    )

    print("=" * 60)


    app.run(
        host=host,
        port=port,
        debug=debug
    )
