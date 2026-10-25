"""Server-side notification writer (service-role, never the browser).

Problem: cross-user match notifications cannot be created by an
end-user client under least-privilege RLS (users may only write
their own inbox). Solution: the Flask server - a trusted backend -
writes them with a service-role client, enforcing authorization
itself:

- The recipient is re-derived server-side from the lost report's
  owner_id. Callers cannot choose who gets notified.
- Both reports are re-read and must exist; the lost report must be
  active and owned. Otherwise nothing is written.
- Title and body are constructed here from match facts, never taken
  from user input.
- The dedupe key makes reprocessing idempotent (23505 = already
  notified, not an error).

The service-role key lives only in the server environment
(SUPABASE_SERVICE_ROLE_KEY). It is never logged, never returned,
and never passed to templates.
"""

import db_config

MATCH_KIND = "match"


def get_notifier():
    """Return notify(lost, found, final) or None when unconfigured.

    None means the server cannot write notifications; callers should
    skip (not fail). No exception, no log of secrets.
    """
    if not db_config.has_service_key():
        return None

    def notify(lost_report, found_report, final_score):
        return notify_match_owner(lost_report, found_report, final_score)

    return notify


def notify_match_owner(lost_report, found_report, final_score):
    """Write one match notification to the lost report's owner.

    Returns the saved row, {"duplicate": True} on reprocess, or None
    when there is no owner to notify. Raises RuntimeError when the
    service key is absent.
    """
    lost = dict(lost_report or {})
    found = dict(found_report or {})
    owner_id = lost.get("owner_id")
    if not owner_id:
        return None
    if not lost.get("id") or not found.get("id"):
        return None

    client = db_config.get_service_client()

    # Re-verify both sides server-side before writing anything.
    fresh_lost = (client.table("reports")
                  .select("id,owner_id,status,report_type")
                  .eq("id", lost["id"]).limit(1).execute().data or [])
    fresh_found = (client.table("reports")
                   .select("id,status,report_type")
                   .eq("id", found["id"]).limit(1).execute().data or [])
    if not fresh_lost or not fresh_found:
        return None
    if (fresh_lost[0].get("owner_id") != owner_id
            or fresh_lost[0].get("status") != "active"
            or fresh_lost[0].get("report_type") != "Lost"
            or fresh_found[0].get("status") != "active"
            or fresh_found[0].get("report_type") != "Found"):
        return None

    try:
        final = float(final_score)
    except (TypeError, ValueError):
        return None

    note = {
        "user_id": owner_id,
        "kind": MATCH_KIND,
        "title": "Possible match for your lost item",
        "body": ("A found %s report scores %.0f%% similarity. "
                 "Open your claims to review it."
                 % (found.get("item_category", "item"), final * 100)),
        "related_report_id": found["id"],
        "dedupe_key": "match:%s:%s" % (found["id"], lost["id"]),
    }
    try:
        response = client.table("notifications").insert(note).execute()
    except Exception as exc:
        if "23505" in str(exc) or "duplicate" in str(exc).lower():
            return {"dedupe_key": note["dedupe_key"], "duplicate": True}
        raise
    saved = response.data or []
    return saved[0] if saved else dict(note)
