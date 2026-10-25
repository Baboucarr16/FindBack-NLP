"""Tests for src/notify.py (fake service client, offline).

Security contract under test: the recipient is always re-derived
server-side from the lost report's owner; callers cannot choose who
gets notified; the service key never appears in messages or outputs.
"""

from types import SimpleNamespace

import pytest

import tests.conftest  # noqa: F401  (path setup)
import db_config
import notify as notify_module
from notify import get_notifier, notify_match_owner


class FakeQuery:
    def __init__(self, table):
        self.table = table
        self.wanted_id = None
        self.inserted = None
        self.fail_with = None

    def select(self, *args):
        return self

    def eq(self, column, value):
        if column == "id":
            self.wanted_id = value
        return self

    def limit(self, count):
        return self

    def insert(self, row):
        self.inserted = row
        self.table.inserted.append(row)
        return self

    def execute(self):
        if self.fail_with is not None:
            raise self.fail_with
        if self.inserted is not None:
            return SimpleNamespace(data=[self.inserted])
        rows = [r for r in self.table.rows if r.get("id") == self.wanted_id]
        return SimpleNamespace(data=rows)


class FakeTable:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.inserted = []

    def select(self, *args):
        return FakeQuery(self)

    def insert(self, row):
        return FakeQuery(self).insert(row)


class FakeService:
    def __init__(self, reports):
        self.tables = {"reports": FakeTable(reports),
                       "notifications": FakeTable()}

    def table(self, name):
        return self.tables[name]


@pytest.fixture()
def service_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-sentinel")


def _service(reports, monkeypatch):
    client = FakeService(reports)
    monkeypatch.setattr(db_config, "get_service_client", lambda: client)
    return client


def test_get_notifier_none_without_key(monkeypatch):
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    assert get_notifier() is None


def test_get_notifier_callable_with_key(service_env):
    assert callable(get_notifier())


def test_service_client_missing_key_error_hides_value(monkeypatch):
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    with pytest.raises(RuntimeError) as excinfo:
        db_config.get_service_client()
    assert "SUPABASE_SERVICE_ROLE_KEY" in str(excinfo.value)


def test_service_client_uses_service_key(monkeypatch, service_env):
    import supabase

    calls = []
    monkeypatch.setattr(supabase, "create_client",
                        lambda url, key: calls.append((url, key)) or object())
    db_config.get_service_client()
    assert calls == [("https://example.supabase.co", "service-sentinel")]


def test_recipient_always_lost_owner(service_env, monkeypatch):
    client = _service([
        {"id": "l1", "owner_id": "owner-A", "status": "active",
         "report_type": "Lost"},
        {"id": "f1", "owner_id": "owner-B", "status": "active",
         "report_type": "Found"},
    ], monkeypatch)
    saved = notify_match_owner(
        {"id": "l1", "owner_id": "owner-A"},
        {"id": "f1", "owner_id": "owner-B",
         "item_category": "Wallet"}, 0.9)
    assert saved["user_id"] == "owner-A"
    assert saved["related_report_id"] == "f1"
    assert saved["dedupe_key"] == "match:f1:l1"
    assert saved["kind"] == "match"
    assert len(client.tables["notifications"].inserted) == 1


def test_no_owner_no_write(service_env, monkeypatch):
    client = _service([], monkeypatch)
    assert notify_match_owner({"id": "l1"}, {"id": "f1"}, 0.9) is None
    assert client.tables["notifications"].inserted == []


def test_changed_owner_blocks_write(service_env, monkeypatch):
    # Lost report now belongs to someone else: stale caller data must
    # not notify the old owner.
    _service([{"id": "l1", "owner_id": "owner-C", "status": "active",
               "report_type": "Lost"},
              {"id": "f1", "owner_id": "owner-B", "status": "active",
               "report_type": "Found"}],
             monkeypatch)
    assert notify_match_owner({"id": "l1", "owner_id": "owner-A"},
                              {"id": "f1"}, 0.9) is None


def test_inactive_or_missing_reports_block_write(service_env, monkeypatch):
    _service([{"id": "l1", "owner_id": "owner-A", "status": "resolved"}],
             monkeypatch)
    assert notify_match_owner({"id": "l1", "owner_id": "owner-A"},
                              {"id": "f1"}, 0.9) is None
    assert notify_match_owner({"id": "l1", "owner_id": "owner-A"},
                              {"id": "missing"}, 0.9) is None


def test_notification_rejects_wrong_report_types(service_env, monkeypatch):
    client = _service([
        {"id": "l1", "owner_id": "owner-A", "status": "active",
         "report_type": "Found"},
        {"id": "f1", "owner_id": "owner-B", "status": "active",
         "report_type": "Lost"},
    ], monkeypatch)
    assert notify_match_owner({"id": "l1", "owner_id": "owner-A"},
                              {"id": "f1"}, 0.9) is None
    assert client.tables["notifications"].inserted == []


def test_duplicate_is_idempotent(service_env, monkeypatch):
    client = _service([
        {"id": "l1", "owner_id": "owner-A", "status": "active",
         "report_type": "Lost"},
        {"id": "f1", "owner_id": "owner-B", "status": "active",
         "report_type": "Found"},
    ], monkeypatch)

    class DupTable(FakeTable):
        def insert(self, row):
            query = FakeQuery(self)
            query.fail_with = RuntimeError("duplicate key (23505)")
            return query

    client.tables["notifications"] = DupTable()
    result = notify_match_owner({"id": "l1", "owner_id": "owner-A"},
                                {"id": "f1"}, 0.9)
    assert result == {"dedupe_key": "match:f1:l1", "duplicate": True}


def test_body_contains_no_caller_text(service_env, monkeypatch):
    client = _service([
        {"id": "l1", "owner_id": "owner-A", "status": "active",
         "report_type": "Lost"},
        {"id": "f1", "owner_id": "owner-B", "status": "active",
         "report_type": "Found"},
    ], monkeypatch)
    notify_match_owner(
        {"id": "l1", "owner_id": "owner-A"},
        {"id": "f1", "item_category": "Wallet",
         "description": "SECRET MARKING hunter2"}, 0.9)
    body = client.tables["notifications"].inserted[0]["body"]
    assert "SECRET" not in body and "hunter2" not in body
