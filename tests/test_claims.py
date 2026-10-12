"""Claim + notification route tests (fake Supabase backend, offline)."""

import sys
import types

import pytest

import tests.conftest  # noqa: F401  (path setup)

if "semantic_matcher" not in sys.modules:
    import pandas as pd

    fake = types.ModuleType("semantic_matcher")
    fake.find_semantic_matches_for_report = (
        lambda lost_report, top_n=5: pd.DataFrame())
    sys.modules["semantic_matcher"] = fake

import app as app_module  # noqa: E402
import store as store_module  # noqa: E402


FOUND_REPORT = {
    "id": "found-1", "owner_id": "owner-9", "report_type": "Found",
    "status": "active", "item_category": "Wallet",
    "description": "brown leather wallet",
}


class FakeClaimsStore:
    def __init__(self, reports=None, claims=None, fail=None):
        self.reports = reports if reports is not None else dict()
        self.claims = claims if claims is not None else []
        self.created = []
        self.decided = []
        self.fail = fail

    def get_report(self, report_id):
        if self.fail:
            raise RuntimeError("db down")
        return self.reports.get(report_id)

    def list_my_claims(self, user_id):
        return [c for c in self.claims if c["claimant_id"] == user_id]

    def list_claims_on_my_reports(self, user_id):
        mine = {rid for rid, rep in self.reports.items()
                if rep.get("owner_id") == user_id}
        return [c for c in self.claims if c["report_id"] in mine]

    def create_claim(self, report_id, claimant_id, note=""):
        for claim in self.claims:
            if (claim["report_id"] == report_id
                    and claim["claimant_id"] == claimant_id):
                raise ValueError(
                    "You have already filed a claim for this report.")
        claim = {"id": "claim-new", "report_id": report_id,
                 "claimant_id": claimant_id, "claim_note": note,
                 "status": "pending"}
        self.created.append(claim)
        return claim

    def decide_claim(self, claim_id, approve, actor_id):
        matches = [c for c in self.claims if c["id"] == claim_id]
        if not matches:
            raise ValueError("Claim not found.")
        claim = matches[0]
        report = self.reports.get(claim["report_id"])
        if report is None or report.get("owner_id") != actor_id:
            raise PermissionError(
                "Only the report owner can decide this claim.")
        if claim["status"] != "pending":
            raise ValueError("Only pending claims can be decided.")
        claim["status"] = "approved" if approve else "rejected"
        self.decided.append((claim_id, approve))
        return claim

    def list_notifications(self, user_id):
        return [{"id": "n1", "title": "Possible match",
                 "body": "A wallet may match your report."}]


@pytest.fixture()
def supabase_mode(monkeypatch):
    monkeypatch.setenv("FINDBACK_STORE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")


@pytest.fixture()
def client():
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


@pytest.fixture()
def logged_in(client):
    with client.session_transaction() as session:
        session["findback_user"] = {"id": "user-1", "email": "u@x.co",
                                    "access_token": "t"}


@pytest.fixture(autouse=True)
def _stub_user_client(monkeypatch):
    # Routes pass this client straight into the (patched) store;
    # the real helper would try to decode the stub token above.
    monkeypatch.setattr(app_module, "get_user_client", lambda: object())


def _use_store(monkeypatch, fake):
    monkeypatch.setattr(store_module, "SupabaseStore",
                        lambda client=None: fake)


def test_claims_require_login(client):
    assert client.get("/claims").status_code == 302
    assert client.get("/claims/new").status_code == 302
    assert client.get("/notifications").status_code == 302


def test_claims_need_supabase_config(client, logged_in, monkeypatch):
    monkeypatch.delenv("FINDBACK_STORE", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    response = client.get("/claims")
    assert b"need Supabase configuration" in response.data


def test_claims_list_shows_both_sections(client, logged_in, supabase_mode,
                                         monkeypatch):
    fake = FakeClaimsStore(
        reports={"found-1": dict(FOUND_REPORT, owner_id="user-1")},
        claims=[{"id": "c1", "report_id": "found-1",
                 "claimant_id": "user-2", "status": "pending"},
                {"id": "c2", "report_id": "found-9",
                 "claimant_id": "user-1", "status": "approved"}])
    _use_store(monkeypatch, fake)
    response = client.get("/claims")
    assert response.status_code == 200
    assert b"c1" in response.data  # incoming claim id
    assert b"found-9" in response.data  # filed claim's report
    assert b"approved" in response.data


def test_claim_form_rejects_own_report(client, logged_in, supabase_mode,
                                       monkeypatch):
    fake = FakeClaimsStore(
        reports={"found-1": dict(FOUND_REPORT, owner_id="user-1")})
    _use_store(monkeypatch, fake)
    response = client.get("/claims/new?report_id=found-1")
    assert b"your own report" in response.data


def test_claim_form_rejects_missing_report(client, logged_in, supabase_mode,
                                           monkeypatch):
    _use_store(monkeypatch, FakeClaimsStore())
    response = client.get("/claims/new?report_id=nope")
    assert b"not found" in response.data


def test_claim_create_and_duplicate(client, logged_in, supabase_mode,
                                    monkeypatch):
    fake = FakeClaimsStore(reports={"found-1": dict(FOUND_REPORT)})
    _use_store(monkeypatch, fake)
    response = client.post("/claims/new", data={
        "report_id": "found-1", "claim_note": "blue stitching inside"})
    assert response.status_code == 302
    assert fake.created[0]["claimant_id"] == "user-1"
    assert fake.created[0]["claim_note"] == "blue stitching inside"

    fake.claims.append(dict(fake.created[0], id="c-old"))
    again = client.post("/claims/new", data={"report_id": "found-1"})
    assert b"already filed" in again.data


def test_claim_decision_owner_and_stranger(client, logged_in, supabase_mode,
                                           monkeypatch):
    owned = FakeClaimsStore(
        reports={"found-1": dict(FOUND_REPORT, owner_id="user-1")},
        claims=[{"id": "c1", "report_id": "found-1",
                 "claimant_id": "user-2", "status": "pending"}])
    _use_store(monkeypatch, owned)
    response = client.post("/claims/c1/decision", data={"action": "approve"})
    assert response.status_code == 302
    assert owned.decided == [("c1", True)]

    foreign = FakeClaimsStore(
        reports={"found-1": dict(FOUND_REPORT, owner_id="owner-9")},
        claims=[{"id": "c1", "report_id": "found-1",
                 "claimant_id": "user-2", "status": "pending"}])
    _use_store(monkeypatch, foreign)
    denied = client.post("/claims/c1/decision", data={"action": "reject"})
    assert b"Only the report owner" in denied.data


def test_claim_decision_rejects_bad_action(client, logged_in, supabase_mode,
                                           monkeypatch):
    _use_store(monkeypatch, FakeClaimsStore())
    response = client.post("/claims/c1/decision", data={"action": "maybe"})
    assert response.status_code == 302


def test_notifications_inbox(client, logged_in, supabase_mode, monkeypatch):
    _use_store(monkeypatch, FakeClaimsStore())
    response = client.get("/notifications")
    assert response.status_code == 200
    assert b"Possible match" in response.data


def test_supabase_found_save_binds_owner(client, logged_in, supabase_mode,
                                         monkeypatch):
    saved = []

    class FakeFoundStore(FakeClaimsStore):
        def save_report(self, payload, owner_id=None):
            saved.append((payload, owner_id))
            return [{"id": "uuid-1234"}]

    _use_store(monkeypatch, FakeFoundStore())
    monkeypatch.setattr(app_module, "get_user_client", lambda: object())
    response = client.post("/found", data={
        "item_category": "Wallet", "description": "brown wallet",
        "organization_type": "Mall", "organization_name": "Mall",
        "campus_or_branch": "Main", "building_or_terminal": "Main",
        "floor_or_level": "G", "specific_area": "Food",
        "date": "2026-08-18", "approx_time": "13:35"})
    assert response.status_code == 200
    assert saved[0][1] == "user-1"
    assert saved[0][0]["report_type"] == "Found"
    assert b"uuid-1234"[:8] in response.data


def test_supabase_found_requires_login(client, supabase_mode, monkeypatch):
    _use_store(monkeypatch, FakeClaimsStore())
    response = client.post("/found", data={
        "item_category": "Wallet", "description": "x",
        "organization_name": "Mall",
        "date": "2026-08-18", "approx_time": "13:35"})
    assert response.status_code == 302
