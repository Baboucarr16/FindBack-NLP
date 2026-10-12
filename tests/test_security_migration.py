"""Offline regression guards for the security hardening migration."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db" / "migrations" / "003_security_and_idempotency.sql"


def test_claim_updates_are_report_owner_only_and_status_only():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    policy = re.search(
        r"create policy claims_update on public\.claims(.*?)"
        r";\s*revoke update on public\.claims",
        sql,
        re.DOTALL,
    )

    assert policy
    assert "select owner_id from public.reports where id = report_id" in policy.group(1)
    assert "claimant_id" not in policy.group(1)
    assert "grant update (status) on public.claims to authenticated" in sql


def test_match_upserts_have_owner_scoped_update_policy():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    policy = re.search(
        r"create policy match_results_update on public\.match_results(.*?)"
        r";\s*-- replace unread-only",
        sql,
        re.DOTALL,
    )

    assert policy
    assert "for update using" in policy.group(1)
    assert "with check" in policy.group(1)
    assert "lost_report_id" in policy.group(1)
    assert "found_report_id" in policy.group(1)
    assert "owner_id" in policy.group(1)
    assert "grant update on public.match_results to authenticated" in sql


def test_notification_dedupe_covers_read_rows_without_deleting_data():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "create unique index if not exists notifications_dedupe_all_uidx" in sql
    assert "on public.notifications (user_id, dedupe_key)" in sql
    assert "where dedupe_key is not null" in sql
    assert "is_read" not in sql
    assert not re.search(r"\bdelete\s+from\s+public\.notifications\b", sql)
