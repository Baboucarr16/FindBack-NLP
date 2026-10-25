"""Route, validation, and CSV-persistence tests for app.py.

The Sentence-BERT engine is stubbed out before importing the app so
these tests are fast and need no network. The production CSV is never
touched: submission tests redirect app.DATASET_FILE into tmp_path.
"""

import csv
import os
import sys
import types

import pandas as pd
import pytest
from flask import session as flask_session

import tests.conftest as conftest  # noqa: F401  (path setup)


def _stub_matcher(rows):
    fake = types.ModuleType("semantic_matcher")

    def find_semantic_matches_for_report(lost_report, top_n=5):
        return pd.DataFrame(rows).head(top_n)

    def find_semantic_matches_against_reports(lost_report, reports, top_n=5):
        return pd.DataFrame(rows).head(top_n)

    fake.find_semantic_matches_for_report = find_semantic_matches_for_report
    fake.find_semantic_matches_against_reports = (
        find_semantic_matches_against_reports)
    sys.modules["semantic_matcher"] = fake


_MATCH_ROWS = [
    {
        "report_id": "FB002",
        "item_category": "Backpack",
        "description": "Found a dark blue bag.",
        "organization_type": "University",
        "organization_name": "Greenfield University",
        "campus_or_branch": "Main Campus",
        "building_or_terminal": "Central Library",
        "floor_or_level": "2nd Floor",
        "specific_area": "Reading Room",
        "date": "2026-08-18",
        "approx_time": "16:45",
        "semantic_score": 0.9,
        "location_score": 1.0,
        "time_score": 1.0,
        "category_score": 1.0,
        "final_score": 0.9,
    },
    {
        "report_id": "FB015",
        "item_category": "Backpack",
        "description": "A navy backpack at the airport.",
        "organization_type": "Airport",
        "organization_name": "Metro International Airport",
        "campus_or_branch": "Terminal 2",
        "building_or_terminal": "Terminal 2",
        "floor_or_level": "Level 3",
        "specific_area": "Departure Hall",
        "date": "2026-08-19",
        "approx_time": "17:30",
        "semantic_score": 0.4,
        "location_score": 0.0,
        "time_score": 0.0,
        "category_score": 1.0,
        "final_score": 0.3,
    },
]

_stub_matcher(_MATCH_ROWS)

import app as app_module  # noqa: E402
from auth import login_session  # noqa: E402


@pytest.fixture()
def client():
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def _search_form(**overrides):
    form = {
        "item_category": "Backpack",
        "description": "lost navy backpack",
        "organization_type": "University",
        "organization_name": "Greenfield University",
        "campus_or_branch": "Main Campus",
        "building_or_terminal": "Central Library",
        "floor_or_level": "2nd Floor",
        "specific_area": "Reading Room",
        "date": "2026-08-18",
        "approx_time": "16:20",
    }
    form.update(overrides)
    return form


def _login(client, user_id="owner-1"):
    with app_module.app.test_request_context():
        login_session({"id": user_id, "email": "owner@example.test",
                       "access_token": "test-access-token",
                       "refresh_token": "test-refresh-token"})
        cookie_user = dict(flask_session["findback_user"])
    with client.session_transaction() as client_session:
        client_session["findback_user"] = cookie_user


def test_homepage_loads(client):
    assert client.get("/").status_code == 200


def test_health_endpoint_is_lightweight_and_does_not_require_database(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_found_form_loads(client):
    assert client.get("/found").status_code == 200


def test_search_requires_category(client):
    response = client.post("/search", data=_search_form(item_category=""))
    assert response.status_code == 200
    assert b"item category" in response.data.lower()


def test_search_requires_description(client):
    response = client.post("/search", data=_search_form(description=""))
    assert response.status_code == 200
    assert b"describe the item" in response.data.lower()


def test_search_rejects_description_as_place(client):
    response = client.post(
        "/search",
        data=_search_form(
            description="lost navy backpack",
            organization_name="I lost my backpack",
        ),
    )
    assert response.status_code == 200
    assert b"Place / Organization" in response.data


def test_search_returns_ranked_candidates_with_disclaimer(client):
    response = client.post("/search", data=_search_form())
    assert response.status_code == 200
    assert b"FB002" in response.data
    assert b"not a" in response.data.lower()  # similarity disclaimer


def test_search_empty_candidates_shows_no_results(client, monkeypatch):
    monkeypatch.setattr(
        app_module,
        "find_semantic_matches_for_report",
        lambda lost_report, top_n=5: pd.DataFrame(),
    )
    response = client.post("/search", data=_search_form())
    assert response.status_code == 200
    assert b"No potential matches found" in response.data


def test_min_score_filter_hides_weak_matches(client, monkeypatch):
    monkeypatch.setenv("FINDBACK_MIN_SCORE", "0.99")
    try:
        response = client.post("/search", data=_search_form())
    finally:
        monkeypatch.delenv("FINDBACK_MIN_SCORE", raising=False)
    assert response.status_code == 200
    assert b"FB002" not in response.data
    assert b"hidden" in response.data.lower()


def _found_form(**overrides):
    form = {
        "item_category": "Wallet",
        "description": "black leather wallet",
        "organization_type": "Mall",
        "organization_name": "City Center Mall",
        "campus_or_branch": "Main Branch",
        "building_or_terminal": "Main Building",
        "floor_or_level": "Ground Floor",
        "specific_area": "Food Court",
        "date": "2026-08-18",
        "approx_time": "13:35",
    }
    form.update(overrides)
    return form


def _isolate_dataset(monkeypatch, tmp_path):
    target = tmp_path / "findback_reports.csv"
    monkeypatch.setattr(app_module, "DATASET_FILE", str(target))
    monkeypatch.setattr(app_module, "DATASET_DIR", str(tmp_path))
    return target


def test_found_submission_creates_unique_ids(client, monkeypatch, tmp_path):
    target = _isolate_dataset(monkeypatch, tmp_path)
    first = client.post("/found", data=_found_form())
    second = client.post("/found", data=_found_form(description="another wallet"))
    assert b"FB001" in first.data
    assert b"FB002" in second.data
    with open(target, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert [row["report_id"] for row in rows] == ["FB001", "FB002"]
    assert rows[0]["description"] == "black leather wallet"


def test_found_submission_preserves_special_characters(client, monkeypatch, tmp_path):
    target = _isolate_dataset(monkeypatch, tmp_path)
    tricky = 'Wallet, black "leather" café ☕, with =formula'
    response = client.post("/found", data=_found_form(description=tricky))
    assert response.status_code == 200
    with open(target, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["description"] == tricky


def test_found_submission_requires_fields(client):
    response = client.post("/found", data=_found_form(description=""))
    assert b"describe the found item" in response.data.lower()


def test_failed_write_does_not_claim_success(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "DATASET_DIR", str(tmp_path))
    # Point the file at a directory so the append fails with OSError.
    monkeypatch.setattr(app_module, "DATASET_FILE", str(tmp_path))
    response = client.post("/found", data=_found_form())
    assert b"Could not save" in response.data
    assert b"FB001" not in response.data


def test_supabase_search_persists_lost_report_and_matches_supabase_found(
        client, monkeypatch):
    import store as store_module
    import notify as notify_module

    monkeypatch.setenv("FINDBACK_STORE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    _login(client)

    class SearchStore:
        def __init__(self, client=None):
            self.saved = None
            self.pairs = []
            self.notifications = []

        def save_report(self, payload, owner_id=None, idempotency_key=None):
            self.saved = (payload, owner_id, idempotency_key)
            return [{"id": "lost-uuid", **payload, "owner_id": owner_id}]

        def list_found(self):
            return [{"id": "found-uuid", "legacy_report_id": "FB900",
                     "report_type": "Found", "status": "active",
                     "item_category": "Backpack", "description": "navy bag",
                     "organization_name": "Greenfield University",
                     "event_date": "2026-08-18", "approx_time": "16:45"}]

        def upsert_match_result(self, pair):
            self.pairs.append(pair)
            return pair

    store = SearchStore()
    monkeypatch.setattr(store_module, "SupabaseStore", lambda client=None: store)
    monkeypatch.setattr(app_module, "get_user_client", lambda: object())
    monkeypatch.setattr(notify_module, "get_notifier", lambda: None)
    monkeypatch.setattr(
        "semantic_matcher.find_semantic_matches_against_reports",
        lambda lost, found, top_n=5: pd.DataFrame([{
            "id": "found-uuid", "report_id": "FB900",
            "item_category": "Backpack", "description": "navy bag",
            "date": "2026-08-18", "approx_time": "16:45",
            "semantic_score": .9, "location_score": .8,
            "time_score": 1., "category_score": 1., "final_score": .9,
        }]),
    )

    response = client.post("/search", data=_search_form())
    assert response.status_code == 200
    assert store.saved[0]["report_type"] == "Lost"
    assert store.saved[0]["event_date"] == "2026-08-18"
    assert store.saved[1] == "owner-1"
    assert store.saved[2]
    assert b"FB900" in response.data
    assert store.pairs[0]["lost_report_id"] == "lost-uuid"
    assert store.pairs[0]["found_report_id"] == "found-uuid"


def test_supabase_search_requires_login_and_does_not_write(
        client, monkeypatch):
    monkeypatch.setenv("FINDBACK_STORE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    response = client.post("/search", data=_search_form())
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_state_changing_posts_require_csrf_outside_test_mode(client):
    app_module.app.config["TESTING"] = False
    try:
        response = client.post("/search", data=_search_form())
    finally:
        app_module.app.config["TESTING"] = True
    assert response.status_code == 400


def test_supabase_search_backend_errors_are_not_rendered(
        client, monkeypatch):
    monkeypatch.setenv("FINDBACK_STORE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    _login(client)

    class BrokenStore:
        def __init__(self, client=None):
            pass

        def save_report(self, *args, **kwargs):
            raise RuntimeError("secret-token SQL policy detail")

    import store as store_module
    monkeypatch.setattr(store_module, "SupabaseStore", BrokenStore)
    monkeypatch.setattr(app_module, "get_user_client", lambda *args: object())
    response = client.post("/search", data=_search_form())
    assert b"Could not save or search reports" in response.data
    assert b"secret-token" not in response.data
