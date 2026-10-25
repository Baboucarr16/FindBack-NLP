"""Tests for src/db_config.py and src/store.py (isolated fixtures)."""

import os

import pytest

import tests.conftest  # noqa: F401  (path setup)
import db_config
from store import CsvStore, SupabaseStore, get_store


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("FINDBACK_STORE", raising=False)


def test_unconfigured_by_default():
    assert db_config.is_configured() is False
    assert db_config.get_supabase_config() == {"url": "", "anon_key": ""}


def test_configured_when_both_vars_set(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    assert db_config.is_configured() is True


def test_url_suffixes_are_normalized(monkeypatch):
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    for raw, clean in (
        ("https://example.supabase.co/rest/v1/",
         "https://example.supabase.co"),
        ("https://example.supabase.co/rest/v1",
         "https://example.supabase.co"),
        ("https://example.supabase.co/auth/v1/",
         "https://example.supabase.co"),
        ("https://example.supabase.co/",
         "https://example.supabase.co"),
        ("https://example.supabase.co",
         "https://example.supabase.co"),
    ):
        monkeypatch.setenv("SUPABASE_URL", raw)
        assert db_config.get_supabase_config()["url"] == clean
    assert db_config.normalize_url("") == ""


def test_client_raises_with_setup_instructions():
    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        db_config.get_client()


def test_csv_store_round_trip(tmp_path):
    path = str(tmp_path / "reports.csv")
    store = CsvStore(path)
    assert store.list_found() == []
    assert store.next_number() == 1
    store.save_found({
        "report_id": "FB001", "report_type": "Found",
        "item_category": "Wallet", "description": "black, leather wallet",
        "organization_name": "Mall",
    })
    store.save_found({
        "report_id": "FB002", "report_type": "Found",
        "item_category": "Phone", "description": "phone",
        "organization_name": "Mall",
    })
    found = store.list_found()
    assert [row["report_id"] for row in found] == ["FB001", "FB002"]
    assert found[0]["description"] == "black, leather wallet"
    assert store.next_number() == 3


def test_supabase_store_fails_fast_without_credentials():
    with pytest.raises(RuntimeError, match="not configured"):
        SupabaseStore()


def test_get_store_defaults_to_csv(tmp_path):
    store = get_store(csv_path=str(tmp_path / "x.csv"))
    assert isinstance(store, CsvStore)


def test_get_store_fails_when_requested_supabase_is_unconfigured(
        monkeypatch, tmp_path):
    monkeypatch.setenv("FINDBACK_STORE", "supabase")
    with pytest.raises(RuntimeError, match="not configured"):
        get_store(csv_path=str(tmp_path / "x.csv"))


def test_no_real_credentials_in_repo():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("db_config.py", "store.py", "auth.py"):
        with open(os.path.join(root, "src", name), encoding="utf-8") as fh:
            content = fh.read().lower()
        assert "service_role" not in content or "never" in content
