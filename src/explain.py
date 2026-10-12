"""Component-level match explanations for FindBack.

explain_match() turns one ranked candidate into human-readable
evidence: per-component contributions plus supporting and
conflicting attributes. It never invents evidence:

- Every statement is derived from the two reports being compared.
- Attributes missing on either side produce no statement.
- Scores are described as similarity, never as probabilities.
- Scoring weights match the live matcher (0.50 / 0.25 / 0.15 / 0.10)
  and are intentionally not tuned here.
"""

# Weights mirror src/matcher.py and src/semantic_matcher.py.
WEIGHTS = (
    ("semantic", "Description", 0.50, "semantic_score"),
    ("location", "Location", 0.25, "location_score"),
    ("time", "Time", 0.15, "time_score"),
    ("category", "Category", 0.10, "category_score"),
)

LOCATION_FIELDS = (
    ("organization_name", "Place"),
    ("campus_or_branch", "Campus / branch"),
    ("building_or_terminal", "Building / terminal"),
    ("floor_or_level", "Floor / level"),
    ("specific_area", "Specific area"),
)


def _norm(value):
    if value is None:
        return ""
    return str(value).strip().lower()


def _present(value):
    return bool(_norm(value))


def _parse_minutes(lost, found):
    """Return absolute minute difference, or None when unavailable."""
    import pandas as pd

    a_date, a_time = _norm(lost.get("date")), _norm(lost.get("approx_time"))
    b_date, b_time = _norm(found.get("date")), _norm(found.get("approx_time"))
    if not a_date or not a_time or not b_date or not b_time:
        return None
    try:
        start = pd.to_datetime(a_date + " " + a_time)
        end = pd.to_datetime(b_date + " " + b_time)
    except Exception:
        return None
    return abs((end - start).total_seconds() / 60)


def explain_match(lost_report, found_record):
    """Build an explanation dict for one lost -> found candidate."""
    lost = dict(lost_report or {})
    found = dict(found_record or {})

    contributions = []
    for key, label, weight, score_field in WEIGHTS:
        try:
            score = float(found.get(score_field, 0.0) or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(1.0, score))
        contributions.append({
            "key": key,
            "label": label,
            "weight": weight,
            "score": score,
            "points": score * weight,
        })

    supporting = []
    conflicting = []

    # Category.
    lost_cat = _norm(lost.get("item_category"))
    found_cat = _norm(found.get("item_category"))
    if lost_cat and found_cat:
        if lost_cat == found_cat:
            supporting.append(
                "Same item category: %s." % found.get("item_category")
            )
        else:
            conflicting.append(
                "Different category (lost: %s, found: %s)."
                % (lost.get("item_category"), found.get("item_category"))
            )

    # Location attributes, field by field.
    for field, label in LOCATION_FIELDS:
        lost_value = _norm(lost.get(field))
        found_value = _norm(found.get(field))
        if not lost_value or not found_value:
            continue
        if lost_value == found_value:
            supporting.append(
                "Matching %s: %s." % (label.lower(), found.get(field))
            )
        elif lost_value in found_value or found_value in lost_value:
            supporting.append(
                "Similar %s (lost: %s, found: %s)."
                % (label.lower(), lost.get(field), found.get(field))
            )
        else:
            conflicting.append(
                "Different %s (lost: %s, found: %s)."
                % (label.lower(), lost.get(field), found.get(field))
            )

    # Time proximity.
    minutes = _parse_minutes(lost, found)
    if minutes is not None:
        if minutes <= 60:
            supporting.append(
                "Found within about %d minutes of the loss."
                % round(minutes)
            )
        elif minutes <= 1440:
            supporting.append(
                "Found same day, about %d hours apart."
                % round(minutes / 60)
            )
        else:
            conflicting.append(
                "Found about %d days apart." % round(minutes / 1440)
            )

    # Description similarity (from the candidate's own score).
    try:
        semantic = float(found.get("semantic_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        semantic = 0.0
    if _present(lost.get("description")) and _present(found.get("description")):
        if semantic >= 0.75:
            supporting.append(
                "Descriptions are highly similar (similarity %d%%)."
                % round(semantic * 100)
            )
        elif semantic >= 0.50:
            supporting.append(
                "Descriptions are moderately similar (similarity %d%%)."
                % round(semantic * 100)
            )
        else:
            conflicting.append(
                "Descriptions show low similarity (similarity %d%%)."
                % round(semantic * 100)
            )

    try:
        final = float(found.get("final_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        final = 0.0

    summary = (
        "%d supporting signal(s), %d conflicting signal(s). "
        "Final score %.1f%% is a weighted similarity, not a probability."
        % (len(supporting), len(conflicting), max(0.0, min(1.0, final)) * 100)
    )

    return {
        "contributions": contributions,
        "supporting": supporting,
        "conflicting": conflicting,
        "summary": summary,
    }
