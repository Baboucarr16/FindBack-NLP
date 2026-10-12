"""Report storage abstraction.

CsvStore preserves the current local behavior (default, no
credentials needed). SupabaseStore is the persistent backend for
deployment; it fails fast with setup instructions when Supabase is
not configured. get_store() picks based on FINDBACK_STORE and
configuration. The Flask app keeps its existing CSV helpers for now;
this module is the tested seam the next milestones build on.
"""

import csv
import os

import db_config

FIELDNAMES = [
    "report_id", "report_type", "item_category", "description",
    "organization_type", "organization_name", "campus_or_branch",
    "building_or_terminal", "floor_or_level", "specific_area",
    "date", "approx_time", "status",
]


class CsvStore:
    """Local CSV backend. Only ever appends; never deletes rows."""

    def __init__(self, path):
        self.path = path

    def list_found(self):
        """Return found reports as dicts (empty list when file missing)."""
        try:
            with open(self.path, "r", encoding="utf-8", newline="") as fh:
                return [row for row in csv.DictReader(fh)
                        if row.get("report_type") == "Found"]
        except FileNotFoundError:
            return []

    def save_found(self, report):
        """Append one found report. Raises OSError on write failure."""
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        exists = os.path.exists(self.path)
        with open(self.path, "a", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
            if not exists:
                writer.writeheader()
            writer.writerow({key: report.get(key, "") for key in FIELDNAMES})

    def next_number(self):
        """Next numeric FB id suffix (1 when no FB rows exist)."""
        numbers = []
        for row in self.list_found_all():
            rid = str(row.get("report_id", "")).strip()
            if rid.startswith("FB"):
                try:
                    numbers.append(int(rid[2:]))
                except ValueError:
                    pass
        return max(numbers) + 1 if numbers else 1

    def list_found_all(self):
        """All rows (lost + found); used for ID generation."""
        try:
            with open(self.path, "r", encoding="utf-8", newline="") as fh:
                return list(csv.DictReader(fh))
        except FileNotFoundError:
            return []


class SupabaseStore:
    """Persistent Supabase backend. Requires configuration.

    Pass an authenticated user client for owner-scoped writes and
    private reads (Row Level Security applies); otherwise the anon
    client is used for public reads.
    """

    def __init__(self, client=None):
        if not db_config.is_configured():
            raise RuntimeError(db_config.NOT_CONFIGURED)
        self.client = client or db_config.get_client()

    def list_found(self):
        response = (self.client.table("reports")
                    .select("*")
                    .eq("report_type", "Found")
                    .eq("status", "active")
                    .execute())
        return response.data

    def list_active_lost(self):
        """Active lost reports (for automatic matching)."""
        response = (self.client.table("reports")
                    .select("*")
                    .eq("report_type", "Lost")
                    .eq("status", "active")
                    .execute())
        return response.data

    def get_report(self, report_id):
        """One report by id, or None. RLS decides visibility."""
        response = (self.client.table("reports")
                    .select("*")
                    .eq("id", report_id)
                    .limit(1)
                    .execute())
        rows = response.data or []
        return rows[0] if rows else None

    def save_report(self, payload, owner_id=None):
        row = dict(payload)
        row["owner_id"] = owner_id
        row["status"] = row.get("status", "active") or "active"
        return self.client.table("reports").insert(row).execute().data

    def list_notifications(self, user_id):
        """Own notifications, newest unread first."""
        response = (self.client.table("notifications")
                    .select("*")
                    .eq("user_id", user_id)
                    .order("created_at", desc=True)
                    .execute())
        return response.data or []

    def upsert_match_result(self, pair):
        """Idempotent pair persistence (unique on lost + found)."""
        response = (self.client.table("match_results")
                    .upsert(pair, on_conflict="lost_report_id,found_report_id")
                    .execute())
        saved = response.data or []
        return saved[0] if saved else dict(pair)

    def create_notification(self, note):
        """Insert one notification; duplicate dedupe keys are ignored."""
        try:
            response = (self.client.table("notifications")
                        .insert(note)
                        .execute())
        except Exception as exc:
            if "23505" in str(exc) or "duplicate" in str(exc).lower():
                return {"dedupe_key": note.get("dedupe_key"),
                        "duplicate": True}
            raise
        saved = response.data or []
        return saved[0] if saved else dict(note)

    # --------------------------------------------------------
    # Claims
    # --------------------------------------------------------

    def create_claim(self, report_id, claimant_id, note=""):
        """File a pending claim. Duplicate claims raise ValueError."""
        try:
            response = (self.client.table("claims")
                        .insert({"report_id": report_id,
                                 "claimant_id": claimant_id,
                                 "claim_note": note or "",
                                 "status": "pending"})
                        .execute())
        except Exception as exc:
            if "23505" in str(exc):
                raise ValueError(
                    "You have already filed a claim for this report."
                ) from exc
            raise
        return (response.data or [None])[0]

    def list_my_claims(self, user_id):
        """Claims filed by this user."""
        response = (self.client.table("claims")
                    .select("*")
                    .eq("claimant_id", user_id)
                    .order("created_at", desc=True)
                    .execute())
        return response.data or []

    def list_claims_on_my_reports(self, user_id):
        """Claims filed on reports owned by this user."""
        mine = (self.client.table("reports")
                .select("id")
                .eq("owner_id", user_id)
                .execute().data or [])
        ids = [row["id"] for row in mine]
        if not ids:
            return []
        response = (self.client.table("claims")
                    .select("*")
                    .in_("report_id", ids)
                    .order("created_at", desc=True)
                    .execute())
        return response.data or []

    def decide_claim(self, claim_id, approve, actor_id):
        """Approve/reject a pending claim. Only the report owner may
        decide; only pending claims may change. Returns the updated
        claim. Raises ValueError / PermissionError otherwise."""
        claims = (self.client.table("claims")
                  .select("*")
                  .eq("id", claim_id)
                  .limit(1)
                  .execute().data or [])
        if not claims:
            raise ValueError("Claim not found.")
        claim = claims[0]
        report = self.get_report(claim["report_id"])
        if report is None or report.get("owner_id") != actor_id:
            raise PermissionError(
                "Only the report owner can decide this claim.")
        validate_claim_transition(claim.get("status", ""), approve)
        response = (self.client.table("claims")
                    .update({"status": "approved" if approve else "rejected"})
                    .eq("id", claim_id)
                    .execute())
        updated = response.data or []
        return updated[0] if updated else dict(
            claim, status="approved" if approve else "rejected")


def validate_claim_transition(old_status, approve):
    """Allowed: pending -> approved / rejected. All else ValueError."""
    new_status = "approved" if approve else "rejected"
    if old_status != "pending":
        raise ValueError(
            "Only pending claims can be decided "
            "(current status: %s)." % (old_status or "unknown"))
    return new_status


def get_store(csv_path=None):
    """Default store: Supabase when requested + configured, else CSV."""
    if (os.environ.get("FINDBACK_STORE", "").strip().lower() == "supabase"
            and db_config.is_configured()):
        return SupabaseStore()
    return CsvStore(csv_path or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "dataset", "findback_reports.csv"))
