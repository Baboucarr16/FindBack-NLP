"""Supabase Auth helpers with honest degraded mode.

Without SUPABASE_URL / SUPABASE_ANON_KEY every operation raises
RuntimeError explaining that authentication is not configured; the
app renders that message instead of failing. No passwords are ever
stored locally - Supabase Auth owns credentials.

Access tokens live only in the signed Flask session (production needs
a strong FLASK_SECRET_KEY and HTTPS). They are required for
user-scoped Supabase requests so Row Level Security applies.
"""

from functools import wraps

from flask import redirect, session, url_for

import db_config

SESSION_KEY = "findback_user"


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


def get_user_client():
    """Supabase client acting as the logged-in user (RLS applies).

    Raises RuntimeError when logged out or unconfigured.
    """
    _require_enabled()
    user = current_user()
    if not user or not user.get("access_token"):
        raise RuntimeError("You must be logged in to do that.")
    client = db_config.get_client()
    client.auth.set_session(
        user["access_token"], user.get("refresh_token") or "")
    return client


def ensure_profile(user_client, user_id, email):
    """Create the profiles row for a user if missing (idempotent)."""
    user_client.table("profiles").upsert(
        {"id": user_id, "email": email or ""}).execute()


def login_session(user):
    """Persist the authenticated user in the Flask session."""
    session[SESSION_KEY] = {
        "id": user["id"],
        "email": user.get("email", ""),
        "access_token": user.get("access_token"),
        "refresh_token": user.get("refresh_token"),
    }
    session.permanent = False


def logout_session():
    """Clear the Flask session."""
    session.pop(SESSION_KEY, None)


def current_user():
    """Return the session user dict, or None when logged out."""
    user = session.get(SESSION_KEY)
    if not isinstance(user, dict) or not user.get("id"):
        return None
    return user


def login_required(view):
    """Redirect anonymous visitors to the login page."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped
