"""SupabaseStore behavior tests with a fake client (offline, no network).

Proves the persistent-backend code paths filter, bind owners, and use
only the anon key - live-project verification still needs real
credentials (see milestone report).
"""

from types import SimpleNamespace

import pytest

import tests.conftest  # noqa: F401  (path setup)
import db_config
from store import SupabaseStore, get_store


class FakeQuery:
    def __init__(self, table, rows=None):
        self.table = table
        self.rows = rows if rows is not None else table.rows
        self.filters = []
        self.inserted = None
        self.updated = None
        self.upserted = None
        self.fail_with = None

    def select(self, *args):
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column, values):
        self.filters.append(("in", column, list(values)))
        return self

    def limit(self, count):
        self.filters.append(("limit", count))
        return self

    def order(self, column, desc=False):
        return self

    def insert(self, row):
        self.inserted = row
        self.table.inserted.append(row)
        return self

    def update(self, row):
        self.updated = row
        return self

    def upsert(self, row, on_conflict=None):
        self.upserted = (row, on_conflict)
        self.table.upserted.append((row, on_conflict))
        return self

    def execute(self):
        if self.fail_with is not None:
            raise self.fail_with
        data = list(self.table.rows)
        for entry in self.filters:
            if entry[0] == "eq":
                _, column, value = entry
                data = [r for r in data if r.get(column) == value]
            elif entry[0] == "in":
                _, column, values = entry
                data = [r for r in data if r.get(column) in values]
            elif entry[0] == "limit":
                data = data[:entry[1]]
        if self.inserted is not None:
            return SimpleNamespace(data=[self.inserted])
        if self.upserted is not None:
            return SimpleNamespace(data=[self.upserted[0]])
        if self.updated is not None:
            for row in data:
                row.update(self.updated)
            return SimpleNamespace(data=data)
        return SimpleNamespace(data=data)


class FakeTable:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.inserted = []
        self.upserted = []

    def select(self, *args):
        return FakeQuery(self)

    def insert(self, row):
        return FakeQuery(self).insert(row)

    def update(self, row):
        return FakeQuery(self).update(row)

    def upsert(self, row, on_conflict=None):
        return FakeQuery(self).upsert(row, on_conflict=on_conflict)


class FakeClient:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return self.tables[name]


@pytest.fixture()
def fake_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.delenv("FINDBACK_STORE", raising=False)


@pytest.fixture()
def fake_client(monkeypatch):
    tables = {"reports": FakeTable([
        {"id": "1", "report_type": "Found", "status": "active"},
        {"id": "2", "report_type": "Lost", "status": "active"},
        {"id": "3", "report_type": "Found", "status": "withdrawn"},
    ])}
    client = FakeClient(tables)
    monkeypatch.setattr(db_config, "get_client", lambda: client)
    return client


def test_list_found_returns_only_active_found(fake_env, fake_client):
    found = SupabaseStore().list_found()
    assert [row["id"] for row in found] == ["1"]
    # Filters behind the query are enforced again here for clarity.
    assert all(row["report_type"] == "Found" and row["status"] == "active"
               for row in found)


def test_save_report_binds_owner_and_defaults_status(fake_env, fake_client):
    saved = SupabaseStore().save_report(
        {"report_type": "Found", "description": "test wallet"},
        owner_id="owner-123")
    assert saved[0]["owner_id"] == "owner-123"
    assert saved[0]["status"] == "active"
    assert fake_client.tables["reports"].inserted[0]["description"] == "test wallet"


def test_save_report_preserves_explicit_status(fake_env, fake_client):
    saved = SupabaseStore().save_report(
        {"report_type": "Lost", "status": "active"}, owner_id="o")
    assert saved[0]["status"] == "active"


def test_save_report_persists_submission_key_and_reuses_existing_row(
        fake_env, fake_client):
    table = fake_client.tables["reports"]
    store = SupabaseStore()
    saved = store.save_report(
        {"report_type": "Lost", "description": "red wallet"},
        owner_id="user-1", idempotency_key="submission-1")
    assert saved[0]["submission_key"] == "submission-1"
    assert saved[0]["owner_id"] == "user-1"
    assert len(table.inserted) == 1

    table.rows.append(saved[0])
    repeated = store.save_report(
        {"report_type": "Lost", "description": "red wallet"},
        owner_id="user-1", idempotency_key="submission-1")
    assert repeated == saved
    assert len(table.inserted) == 1


def test_get_store_selects_supabase_when_configured(fake_env):
    import os
    os.environ["FINDBACK_STORE"] = "supabase"
    try:
        assert isinstance(get_store(), SupabaseStore)
    finally:
        del os.environ["FINDBACK_STORE"]


def test_client_creation_uses_anon_key_only(monkeypatch):
    # db_config imports create_client lazily inside get_client(), so
    # patching the attribute is enough - no reloads, no network.
    import supabase

    calls = []
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key-value")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-sentinel")

    class Dummy:
        pass

    def recorder(url, key):
        calls.append((url, key))
        return Dummy()

    monkeypatch.setattr(supabase, "create_client", recorder)
    db_config.get_client()
    assert calls, "expected create_client to be called"
    for url, key in calls:
        assert url == "https://example.supabase.co"
        assert key == "anon-key-value"
        assert "sentinel" not in key


@pytest.fixture()
def claim_tables(monkeypatch):
    tables = {
        "reports": FakeTable([
            {"id": "r1", "owner_id": "owner-1", "report_type": "Found",
             "status": "active"},
        ]),
        "claims": FakeTable([
            {"id": "c1", "report_id": "r1", "claimant_id": "user-2",
             "status": "pending"},
        ]),
        "notifications": FakeTable(),
        "match_results": FakeTable(),
    }
    monkeypatch.setattr(db_config, "get_client",
                        lambda: FakeClient(tables))
    return tables


def test_get_report_returns_row_or_none(fake_env, claim_tables):
    store = SupabaseStore()
    assert store.get_report("r1")["owner_id"] == "owner-1"
    assert store.get_report("missing") is None


def test_list_active_lost_filters(fake_env, claim_tables):
    claim_tables["reports"].rows.append(
        {"id": "r2", "report_type": "Lost", "status": "active"})
    store = SupabaseStore()
    assert [row["id"] for row in store.list_active_lost()] == ["r2"]


def test_create_claim_duplicate_maps_to_value_error(fake_env, claim_tables):
    store = SupabaseStore()

    class DupTable(FakeTable):
        def insert(self, row):
            query = FakeQuery(self)
            query.fail_with = RuntimeError(
                'duplicate key value violates unique constraint '
                '"claims_report_id_claimant_id_key" (23505)')
            return query

    claim_tables["claims"] = DupTable(claim_tables["claims"].rows)
    # Rebind: SupabaseStore already holds the FakeClient, whose
    # table() reads the live dict, so replacement is visible.
    with pytest.raises(ValueError, match="already filed"):
        store.create_claim("r1", "user-2", "note")


def test_decide_claim_owner_only_and_pending(fake_env, claim_tables):
    store = SupabaseStore()
    updated = store.decide_claim("c1", True, "owner-1")
    assert updated["status"] == "approved"
    with pytest.raises(PermissionError, match="report owner"):
        store.decide_claim("c1", False, "user-2")
    with pytest.raises(ValueError, match="not found"):
        store.decide_claim("nope", True, "owner-1")


def test_claim_transitions_allow_only_pending(fake_env, claim_tables):
    from store import validate_claim_transition

    assert validate_claim_transition("pending", True) == "approved"
    assert validate_claim_transition("pending", False) == "rejected"
    with pytest.raises(ValueError, match="pending"):
        validate_claim_transition("approved", True)
    with pytest.raises(ValueError, match="pending"):
        validate_claim_transition("withdrawn", False)
    with pytest.raises(ValueError, match="pending"):
        validate_claim_transition("", True)


def test_upsert_match_result_uses_pair_conflict(fake_env, claim_tables):
    store = SupabaseStore()
    pair = {"lost_report_id": "l1", "found_report_id": "f1",
            "final_score": 0.8}
    assert store.upsert_match_result(pair)["final_score"] == 0.8
    assert claim_tables["match_results"].upserted[0][1] == \
        "lost_report_id,found_report_id"


def test_create_notification_swallows_duplicates(fake_env, claim_tables):
    store = SupabaseStore()
    note = {"user_id": "u", "dedupe_key": "k"}
    assert store.create_notification(note)["dedupe_key"] == "k"

    class DupTable(FakeTable):
        def insert(self, row):
            query = FakeQuery(self)
            query.fail_with = RuntimeError("duplicate key (23505)")
            return query

    claim_tables["notifications"] = DupTable()
    assert store.create_notification(note)["duplicate"] is True
