"""Auth route + session tests (Supabase stubbed out / disabled)."""

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
from auth import (  # noqa: E402
    current_user,
    friendly_auth_error,
    login_required,
    login_session,
    logout_session,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)


@pytest.fixture()
def client():
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def test_secret_key_is_set():
    assert app_module.app.secret_key


def test_register_page_notes_disabled_auth(client):
    response = client.get("/register")
    assert response.status_code == 200
    assert b"not configured" in response.data.lower()


def test_login_page_notes_disabled_auth(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b"not configured" in response.data.lower()


def test_register_validates_email(client):
    response = client.post("/register", data={
        "email": "not-an-email", "password": "secret12"})
    assert b"valid email" in response.data.lower()


def test_register_validates_password(client):
    response = client.post("/register", data={
        "email": "a@b.co", "password": "short"})
    assert b"at least 6" in response.data.lower()


def test_register_without_credentials_is_honest(client):
    response = client.post("/register", data={
        "email": "a@b.co", "password": "secret12"})
    assert b"not configured" in response.data.lower()
    with client.session_transaction() as session:
        assert session.get("findback_user") is None


def test_login_requires_fields(client):
    response = client.post("/login", data={"email": "", "password": ""})
    assert b"email and password" in response.data.lower()


def test_login_without_credentials_is_honest(client):
    response = client.post("/login", data={
        "email": "a@b.co", "password": "secret12"})
    assert b"not configured" in response.data.lower()


def test_session_round_trip():
    with app_module.app.test_request_context():
        assert current_user() is None
        login_session({"id": "user-1", "email": "a@b.co",
                       "access_token": "tok", "refresh_token": "ref",
                       "confirmed": True})
        assert current_user()["id"] == "user-1"
        assert current_user()["email"] == "a@b.co"
        assert current_user()["access_token"] == "tok"
        logout_session()
        assert current_user() is None


def test_session_without_id_is_anonymous():
    with app_module.app.test_request_context():
        login_session({"id": "", "email": "a@b.co"})
        assert current_user() is None


def test_friendly_auth_errors():
    assert "wait" in friendly_auth_error(
        Exception("email rate limit exceeded")).lower()
    assert "confirm" in friendly_auth_error(
        Exception("Email not confirmed")).lower()
    assert "already registered" in friendly_auth_error(
        Exception("User already registered")).lower()
    assert "incorrect email or password" in friendly_auth_error(
        Exception("Invalid login credentials")).lower()
    assert "try again later" in friendly_auth_error(
        Exception("something completely unexpected")).lower()


def test_login_maps_invalid_credentials(monkeypatch, client):
    def boom(email, password):
        raise Exception("Invalid login credentials")
    monkeypatch.setattr(app_module, "sign_in", boom)
    response = client.post("/login", data={
        "email": "a@b.co", "password": "secret12"})
    assert b"incorrect email or password" in response.data.lower()
    with client.session_transaction() as session:
        assert session.get("findback_user") is None


def test_register_unconfirmed_shows_message_not_session(
        monkeypatch, client):
    def fake_sign_up(email, password):
        return {"id": "u-1", "email": email, "access_token": None,
                "refresh_token": None, "confirmed": False}
    monkeypatch.setattr(app_module, "sign_up", fake_sign_up)
    response = client.post("/register", data={
        "email": "a@b.co", "password": "secret12"})
    assert b"confirmation" in response.data.lower()
    with client.session_transaction() as session:
        assert session.get("findback_user") is None


def test_login_syncs_profile_but_survives_sync_failure(
        monkeypatch, client):
    def fake_sign_in(email, password):
        return {"id": "u-1", "email": email, "access_token": "t",
                "refresh_token": "r", "confirmed": True}
    monkeypatch.setattr(app_module, "sign_in", fake_sign_in)
    monkeypatch.setattr(app_module, "get_user_client",
                        lambda: object())

    synced = []

    def boom(client_obj, uid, email):
        synced.append(uid)
        raise RuntimeError("db down")

    monkeypatch.setattr(app_module, "ensure_profile", boom)
    response = client.post("/login", data={
        "email": "a@b.co", "password": "secret12"})
    assert response.status_code == 302  # login still succeeds
    assert synced == ["u-1"]
    with client.session_transaction() as session:
        assert session.get("findback_user")["id"] == "u-1"


def test_login_required_redirects_anonymous():
    @login_required
    def view():
        return "secret"

    with app_module.app.test_request_context():
        response = view()
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")


def test_login_required_passes_authenticated():
    @login_required
    def view():
        return "secret"

    with app_module.app.test_request_context():
        login_session({"id": "u-1", "email": "a@b.co"})
        assert view() == "secret"


def test_logout_redirects_home(client):
    response = client.get("/logout")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
