"""Auth route + session tests (Supabase stubbed out / disabled)."""

import sys
import types

import pytest
from flask import session

import tests.conftest  # noqa: F401  (path setup)

if "semantic_matcher" not in sys.modules:
    import pandas as pd

    fake = types.ModuleType("semantic_matcher")
    fake.find_semantic_matches_for_report = (
        lambda lost_report, top_n=5: pd.DataFrame())
    fake.find_semantic_matches_against_reports = (
        lambda lost_report, reports, top_n=5: pd.DataFrame())
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
        assert "access_token" not in session["findback_user"]
        assert "refresh_token" not in session["findback_user"]
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


def test_login_does_not_create_session_when_profile_sync_fails(
        monkeypatch, client):
    def fake_sign_in(email, password):
        return {"id": "u-1", "email": email, "access_token": "t",
                "refresh_token": "r", "confirmed": True}
    monkeypatch.setattr(app_module, "sign_in", fake_sign_in)
    monkeypatch.setattr(app_module, "get_user_client",
                        lambda user=None: object())

    synced = []

    def boom(client_obj, uid, email):
        synced.append(uid)
        raise RuntimeError("db down")

    monkeypatch.setattr(app_module, "ensure_profile", boom)
    response = client.post("/login", data={
        "email": "a@b.co", "password": "secret12"})
    assert response.status_code == 200
    assert b"could not finish setting up" in response.data.lower()
    assert synced == ["u-1"]
    with client.session_transaction() as session:
        assert session.get("findback_user") is None


def test_login_cookie_does_not_contain_auth_tokens(monkeypatch, client):
    def fake_sign_in(email, password):
        return {"id": "u-1", "email": email, "access_token": "ACCESS_SECRET",
                "refresh_token": "REFRESH_SECRET", "confirmed": True}

    monkeypatch.setattr(app_module, "sign_in", fake_sign_in)
    monkeypatch.setattr(app_module, "get_user_client",
                        lambda user=None: object())
    monkeypatch.setattr(app_module, "ensure_profile", lambda *args: None)
    response = client.post("/login", data={
        "email": "a@b.co", "password": "secret12"})
    cookie = response.headers.get("Set-Cookie", "")
    assert "ACCESS_SECRET" not in cookie
    assert "REFRESH_SECRET" not in cookie


def test_supabase_user_client_persists_rotated_tokens(monkeypatch):
    from types import SimpleNamespace
    import auth as auth_module

    client = SimpleNamespace(auth=SimpleNamespace())
    client.auth.set_session = lambda access, refresh: SimpleNamespace(
        session=SimpleNamespace(access_token="rotated-access",
                                refresh_token="rotated-refresh"))
    client.auth.get_session = lambda: SimpleNamespace(
        access_token="rotated-access", refresh_token="rotated-refresh")
    monkeypatch.setattr(auth_module.db_config, "get_client", lambda: client)
    monkeypatch.setattr(auth_module.db_config, "is_configured", lambda: True)

    with app_module.app.test_request_context():
        login_session({"id": "u-1", "email": "u@example.test",
                       "access_token": "old-access",
                       "refresh_token": "old-refresh"})
        result = auth_module.get_user_client()
        assert result is client
        assert current_user()["access_token"] == "rotated-access"
        assert current_user()["refresh_token"] == "rotated-refresh"


def test_invalid_refresh_token_clears_local_login(monkeypatch):
    import auth as auth_module

    client = types.SimpleNamespace(auth=types.SimpleNamespace())
    client.auth.set_session = lambda access, refresh: (_ for _ in ()).throw(
        RuntimeError("Invalid Refresh Token: Refresh Token Not Found"))
    monkeypatch.setattr(auth_module.db_config, "get_client", lambda: client)
    monkeypatch.setattr(auth_module.db_config, "is_configured", lambda: True)
    with app_module.app.test_request_context():
        login_session({"id": "u-1", "access_token": "old",
                       "refresh_token": "expired"})
        with pytest.raises(RuntimeError, match="log in again"):
            auth_module.get_user_client()
        assert current_user() is None


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
    response = client.post("/logout")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_logout_revokes_current_supabase_session(monkeypatch):
    import auth as auth_module

    calls = []
    fake_client = types.SimpleNamespace(auth=types.SimpleNamespace())
    fake_client.auth.set_session = lambda access, refresh: calls.append(
        ("set", access, refresh))
    fake_client.auth.sign_out = lambda options: calls.append(
        ("sign_out", options))
    monkeypatch.setattr(auth_module.db_config, "is_configured", lambda: True)
    monkeypatch.setattr(auth_module.db_config, "get_client",
                        lambda: fake_client)
    with app_module.app.test_request_context():
        login_session({"id": "u-1", "access_token": "access",
                       "refresh_token": "refresh"})
        logout_session()
        assert current_user() is None
    assert calls == [("set", "access", "refresh"),
                     ("sign_out", {"scope": "local"})]


def test_production_session_cookie_security_defaults():
    assert app_module.app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app_module.app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
