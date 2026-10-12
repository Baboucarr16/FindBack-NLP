"""Automatic matching of a new found report against active lost reports.

Reuses the live weighting scheme (description 0.50 / location 0.25 /
time 0.15 / category 0.10) with TF-IDF text similarity so no model
download is needed here; the scoring function is injectable for tests.
Weights are intentionally unchanged - no evaluation evidence supports
retuning.

Writes are idempotent: match pairs upsert on (lost, found) and
notifications carry a dedupe key covered by a partial unique index,
so reprocessing the same report never duplicates rows.

The notify cutoff defaults to 0.60 and is explicitly UNTUNED; set
FINDBACK_NOTIFY_MIN_SCORE from real labeled development data.
"""

import os
import re

W_DESC, W_LOC, W_TIME, W_CAT = 0.50, 0.25, 0.15, 0.10


def _clean(text):
    text = str(text or "").lower().replace("-", " ")
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _norm(value):
    return str(value or "").strip().lower()


def _location_score(lost, found):
    weights = {"organization_name": 0.30, "campus_or_branch": 0.15,
               "building_or_terminal": 0.20, "floor_or_level": 0.10,
               "specific_area": 0.25}
    total, matched = 0.0, 0.0
    for field, weight in weights.items():
        first, second = _norm(lost.get(field)), _norm(found.get(field))
        if not first or not second:
            continue
        total += weight
        if first == second or first in second or second in first:
            matched += weight
    return matched / total if total else 0.0


def _category_score(lost, found):
    first, second = _norm(lost.get("item_category")), _norm(found.get("item_category"))
    if not first or not second:
        return 0.0
    return 1.0 if first == second else 0.0


def _time_score(lost, found):
    """Same buckets as the live matcher (30m / 1h / 2h / 6h / 24h)."""
    import datetime

    def parse(report):
        date = _norm(report.get("event_date") or report.get("date"))
        time = _norm(report.get("approx_time"))
        if not date or not time:
            return None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.datetime.strptime(
                    "%s %s" % (date, time), fmt)
            except ValueError:
                continue
        return None

    start, end = parse(lost), parse(found)
    if start is None or end is None:
        return 0.0
    minutes = abs((end - start).total_seconds() / 60)
    if minutes <= 30:
        return 1.0
    if minutes <= 60:
        return 0.8
    if minutes <= 120:
        return 0.5
    if minutes <= 360:
        return 0.25
    if minutes <= 1440:
        return 0.10
    return 0.0


def default_score_fn(lost_reports, found_report):
    """Score every lost report against one found report.

    Returns {lost_id: component-score dict}. TF-IDF is fitted on the
    batch only (no app dataset, no network).
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    descriptions = [_clean(found_report.get("description"))]
    descriptions += [_clean(lost.get("description")) for lost in lost_reports]
    try:
        matrix = TfidfVectorizer().fit_transform(descriptions)
        sims = cosine_similarity(matrix[0:1], matrix[1:]).flatten().tolist()
    except ValueError:
        sims = [0.0] * len(lost_reports)

    scores = {}
    for lost, semantic in zip(lost_reports, sims):
        location = _location_score(lost, found_report)
        time = _time_score(lost, found_report)
        category = _category_score(lost, found_report)
        scores[lost["id"]] = {
            "semantic_score": float(semantic),
            "location_score": location,
            "time_score": time,
            "category_score": category,
            "final_score": (semantic * W_DESC + location * W_LOC
                            + time * W_TIME + category * W_CAT),
        }
    return scores


def notify_min_score():
    """Untuned notification cutoff, configurable via environment."""
    try:
        return float(os.environ.get("FINDBACK_NOTIFY_MIN_SCORE", "0.60"))
    except ValueError:
        return 0.60


def _safe(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except Exception:
        return None


def process_new_found_report(found_report, store,
                             score_fn=None, min_score=None,
                             notify_fn="store"):
    """Match, persist pairs, and notify owners. Best-effort: never raises.

    notify_fn selects the notification path: "store" (default) writes
    through the store (needs insert rights), a callable
    notify(lost, found, final) is used instead (e.g. the server-side
    service-role writer from src/notify.py), and None skips
    notifications while counting them as skipped.

    Returns {"matches", "notifications", "skipped", "errors"}.
    """
    summary = {"matches": 0, "notifications": 0, "skipped": 0, "errors": 0}
    score_fn = score_fn or default_score_fn
    cutoff = notify_min_score() if min_score is None else min_score

    lost_reports = _safe(store.list_active_lost) or []
    if not lost_reports:
        return summary
    try:
        scores = score_fn(lost_reports, found_report) or {}
    except Exception:
        summary["errors"] += 1
        return summary

    for lost in lost_reports:
        components = scores.get(lost.get("id"), {})
        try:
            final = float(components.get("final_score", 0.0))
        except (TypeError, ValueError):
            summary["errors"] += 1
            continue
        if final < cutoff:
            continue
        pair = {
            "lost_report_id": lost.get("id"),
            "found_report_id": found_report.get("id"),
            "semantic_score": components.get("semantic_score", 0.0),
            "location_score": components.get("location_score", 0.0),
            "time_score": components.get("time_score", 0.0),
            "category_score": components.get("category_score", 0.0),
            "final_score": final,
        }
        saved = _safe(store.upsert_match_result, pair)
        if saved is None:
            summary["errors"] += 1
            continue
        summary["matches"] += 1
        owner_id = lost.get("owner_id")
        if not owner_id:
            continue
        if notify_fn is None:
            summary["skipped"] += 1
            continue
        if callable(notify_fn):
            try:
                note = notify_fn(lost, found_report, final)
            except Exception:
                summary["errors"] += 1
                continue
        else:
            note = _safe(store.create_notification, {
                "user_id": owner_id,
                "kind": "match",
                "title": "Possible match for your lost item",
                "body": ("A found %s report scores %.0f%% similarity. "
                         "Open your claims to review it."
                         % (found_report.get("item_category", "item"),
                            final * 100)),
                "related_report_id": found_report.get("id"),
                "dedupe_key": "match:%s:%s" % (
                    found_report.get("id"), lost.get("id")),
            })
        if note is None:
            summary["errors"] += 1
        elif isinstance(note, dict) and note.get("duplicate"):
            pass  # idempotent reprocess: already notified
        else:
            summary["notifications"] += 1
    return summary
