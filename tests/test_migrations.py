"""Migration-file drift guards (no database needed).

These tests pin the contract between the app code and the SQL the
owner applies in the Supabase dashboard: policy names referenced by
behavioral tests must exist in the migration files.
"""

import os
import re

import tests.conftest  # noqa: F401  (path setup)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(ROOT, "db", name), encoding="utf-8") as fh:
        return fh.read()


def test_schema_defines_all_five_tables():
    schema = _read("schema.sql")
    for table in ("profiles", "reports", "match_results", "claims",
                  "notifications"):
        assert re.search(r"create table if not exists public\.%s" % table,
                         schema), table


def test_schema_enables_rls_everywhere():
    schema = _read("schema.sql").lower()
    for table in ("profiles", "reports", "match_results", "claims",
                  "notifications"):
        assert ("enable row level security" in schema)


def test_write_policies_cover_claims_lifecycle():
    schema = _read("schema.sql")
    assert "claims_insert_self_on_found" in schema
    assert "claims_update_participant_status" in schema
    assert "reports_insert_owner" in schema


def test_match_notify_migration_adds_insert_policies():
    migration = _read(os.path.join("migrations",
                                   "002_match_notify_writes.sql"))
    assert "match_results_insert" in migration
    assert "notifications_insert_own" in migration


def test_core_security_migration_removes_public_profile_and_match_reads():
    from pathlib import Path

    sql = (Path(__file__).resolve().parents[1]
           / "db" / "migrations" / "004_core_dataflow_security.sql")
    migration = sql.read_text(encoding="utf-8").lower()
    assert "profiles_read_self" in migration
    assert "match_results_read_participants" in migration
    assert "claimant_id = (select auth.uid())" in migration
    assert "with check" in migration
    assert "submission_key" in migration
    assert "create policy notifications_insert_own" not in migration
    assert "(select auth.uid()) = user_id" in migration
    # Least privilege: pair inserts must be scoped to reports the
    # writer owns, never open to any signed-in user.
    assert "owner_id" in migration
    assert "found_report_id" in migration
    assert "auth.uid() is not null" not in migration.lower()


def test_claim_policy_requires_pending_found_report_and_owner_decisions():
    migration = _read(os.path.join(
        "migrations", "004_core_dataflow_security.sql")).lower()
    insert_policy = migration.split(
        "create policy claims_insert_self_on_found", 1)[1].split(
            ";", 1)[0]
    update_policy = migration.split(
        "create policy claims_update_participant_status", 1)[1].split(
            ";", 1)[0]
    assert "claimant_id = (select auth.uid())" in insert_policy
    assert "status = 'pending'" in insert_policy
    assert "report_type = 'found'" in insert_policy
    assert "owner_id <> (select auth.uid())" in insert_policy
    assert "status in ('approved', 'rejected')" in update_policy
    assert "owner_id = (select auth.uid())" in update_policy
    assert "grant insert (report_id, claimant_id, claim_note)" in migration
    assert "grant update (status) on public.claims" in migration
    assert "create policy notifications_insert_own" not in migration
