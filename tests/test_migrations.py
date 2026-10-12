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
    assert "claims_insert" in schema
    assert "claims_update" in schema
    assert "reports_insert" in schema


def test_match_notify_migration_adds_insert_policies():
    migration = _read(os.path.join("migrations",
                                   "002_match_notify_writes.sql"))
    assert "match_results_insert" in migration
    assert "notifications_insert_own" in migration
    assert "auth.uid() = user_id" in migration
    # Least privilege: pair inserts must be scoped to reports the
    # writer owns, never open to any signed-in user.
    assert "owner_id" in migration
    assert "found_report_id" in migration
    assert "auth.uid() is not null" not in migration.lower()
