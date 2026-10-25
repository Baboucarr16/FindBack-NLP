"""Supabase Auth helpers with honest degraded mode.

Without SUPABASE_URL / SUPABASE_ANON_KEY every operation raises
RuntimeError explaining that authentication is not configured; the
app renders that message instead of failing. No passwords are ever
stored locally - Supabase Auth owns credentials.

Access/refresh tokens live in server-side process memory. Flask's
signed browser cookie contains only an opaque session handle and basic
display metadata. The current deployment contract uses one Gunicorn
worker; multi-worker deployments need a shared server-side session
store. Production needs a strong FLASK_SECRET_KEY and HTTPS.
"""

from functools import wraps
import secrets
import threading

from flask import redirect, session, url_for

import db_config

SESSION_KEY = "findback_user"
_AUTH_SESSIONS = {}
_AUTH_SESSIONS_LOCK = threading.Lock()


def _session_value(auth_session, name):
    if isinstance(auth_session, dict):
        return auth_session.get(name)
    return getattr(auth_session, name, None)


def _clear_local_auth_session(session_id=None):
    if session_id:
        with _AUTH_SESSIONS_LOCK:
            _AUTH_SESSIONS.pop(session_id, None)
    session.clear()


def is_enabled():
    """True when Supabase Auth can be used."""
    return db_config.is_configured()


def _require_enabled():
    if not is_enabled():
        raise RuntimeError(
            "Authentication is not configured. Set SUPABASE_URL and "
            "SUPABASE_ANON_KEY in the environment (see .env.example)."
        )


def friendly_auth_error(exc):
    """Map Supabase Auth failures to plain, non-technical messages."""
    message = str(exc).lower()
    if "rate limit" in message:
        return ("Too many attempts. Please wait a while "
                "and try again.")
    if "not confirmed" in message or "confirm" in message:
        return ("Your email address is not confirmed yet. "
                "Please check your inbox for the confirmation link, "
                "then log in.")
    if "already registered" in message or "already exists" in message:
        return ("This email is already registered. "
                "Try logging in instead.")
    if "invalid login credentials" in message:
        return "Incorrect email or password. Please try again."
    if "password" in message and ("short" in message or "length" in message):
        return "Password must be at least 6 characters."
    return "Authentication failed. Please try again later."


def _user_payload(response):
    user = response.user
    auth_session = getattr(response, "session", None)
    return {
        "id": user.id,
        "email": user.email,
        "access_token": getattr(auth_session, "access_token", None),
        "refresh_token": getattr(auth_session, "refresh_token", None),
        "confirmed": auth_session is not None,
    }


def sign_up(email, password):
    """Register a user via Supabase Auth. Returns the user payload.

    When the project requires email confirmation there is no session
    yet (confirmed=False); callers must NOT log the user in until the
    address is confirmed.
    """
    _require_enabled()
    client = db_config.get_client()
    return _user_payload(client.auth.sign_up(
        {"email": email, "password": password}))


def sign_in(email, password):
    """Log a user in via Supabase Auth. Returns the user payload."""
    _require_enabled()
    client = db_config.get_client()
    return _user_payload(client.auth.sign_in_with_password(
        {"email": email, "password": password}))


def get_user_client(authenticated_user=None):
    """Supabase client acting as the logged-in user (RLS applies).

    Raises RuntimeError when logged out or unconfigured.
    """
    _require_enabled()
    user = authenticated_user or current_user()
    if not user or not user.get("access_token"):
        raise RuntimeError("You must be logged in to do that.")
    client = db_config.get_client()
    try:
        auth_response = client.auth.set_session(
            user["access_token"], user.get("refresh_token") or "")
    except Exception as exc:
        message = str(exc).lower()
        invalid_token = any(marker in message for marker in (
            "invalid refresh token", "refresh token not found",
            "invalid jwt", "jwt expired", "session not found"))
        if invalid_token and authenticated_user is None:
            _clear_local_auth_session(user.get("session_id"))
        raise RuntimeError(
            "Your session could not be verified. Please log in again."
        ) from None
    refreshed = _session_value(auth_response, "session")
    if refreshed is None:
        refreshed = client.auth.get_session()
    access_token = _session_value(refreshed, "access_token")
    refresh_token = _session_value(refreshed, "refresh_token")
    if access_token and refresh_token and authenticated_user is None:
        session_id = user.get("session_id")
        if session_id:
            with _AUTH_SESSIONS_LOCK:
                auth_state = _AUTH_SESSIONS.get(session_id)
                if auth_state:
                    auth_state["access_token"] = access_token
                    auth_state["refresh_token"] = refresh_token
    return client


def ensure_profile(user_client, user_id, email):
    """Create the user's profile when absent without broad update rights."""
    table = user_client.table("profiles")
    existing = (table.select("id").eq("id", user_id)
                .limit(1).execute().data or [])
    if existing:
        return existing[0]
    try:
        return table.insert({"id": user_id,
                             "email": email or ""}).execute()
    except Exception as exc:
        if "23505" not in str(exc) and "duplicate" not in str(exc).lower():
            raise
        existing = (table.select("id").eq("id", user_id)
                    .limit(1).execute().data or [])
        if existing:
            return existing[0]
        raise


def login_session(user):
    """Persist the authenticated user in the Flask session."""
    old_user = current_user()
    if old_user and old_user.get("session_id"):
        with _AUTH_SESSIONS_LOCK:
            _AUTH_SESSIONS.pop(old_user["session_id"], None)
    session.clear()
    session_id = secrets.token_urlsafe(32)
    auth_state = {
        "id": user["id"],
        "email": user.get("email", ""),
        "access_token": user.get("access_token"),
        "refresh_token": user.get("refresh_token"),
    }
    with _AUTH_SESSIONS_LOCK:
        _AUTH_SESSIONS[session_id] = auth_state
    session[SESSION_KEY] = {
        "id": user["id"],
        "email": user.get("email", ""),
        "session_id": session_id,
    }
    session.permanent = False


def logout_session():
    """Revoke the current Supabase session, then clear the Flask cookie."""
    user = current_user()
    if user and user.get("access_token") and user.get("refresh_token"):
        try:
            client = db_config.get_client()
            client.auth.set_session(user["access_token"],
                                    user["refresh_token"])
            client.auth.sign_out({"scope": "local"})
        except Exception:
            # Local logout must still complete even if Auth is unavailable.
            pass
    cookie_user = session.get(SESSION_KEY)
    session_id = (cookie_user.get("session_id")
                  if isinstance(cookie_user, dict) else None)
    _clear_local_auth_session(session_id)


def current_user():
    """Return the session user dict, or None when logged out."""
    cookie_user = session.get(SESSION_KEY)
    if (not isinstance(cookie_user, dict) or not cookie_user.get("id")
            or not cookie_user.get("session_id")):
        return None
    with _AUTH_SESSIONS_LOCK:
        auth_state = _AUTH_SESSIONS.get(cookie_user["session_id"])
        if not auth_state or auth_state.get("id") != cookie_user["id"]:
            return None
        return dict(cookie_user, **auth_state)


def login_required(view):
    """Redirect anonymous visitors to the login page."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped
