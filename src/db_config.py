"""Supabase configuration, read from the environment.

No secrets live in code or in Git: copy .env.example to .env locally
and set SUPABASE_URL / SUPABASE_ANON_KEY. Without them the app runs
in local CSV mode (see db/README.md).
"""

import os


def _load_local_env():
    """Load the repo-root .env if present (local development only).

    Silent when python-dotenv is not installed. Never overrides real
    environment variables.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(root, ".env"))


_load_local_env()

NOT_CONFIGURED = (
    "Supabase is not configured. Set SUPABASE_URL and "
    "SUPABASE_ANON_KEY in the environment (see .env.example). "
    "The app continues to run in local CSV mode."
)


def normalize_url(url):
    """Return a bare project URL (no API path suffix, no trailing slash).

    Users sometimes paste a URL copied from a REST example such as
    https://xyz.supabase.co/rest/v1/ ; the client libraries append
    those paths themselves, so the suffixes are stripped here.
    """
    url = (url or "").strip().rstrip("/")
    lowered = url.lower()
    for suffix in ("/rest/v1", "/auth/v1", "/storage/v1",
                   "/realtime/v1", "/functions/v1"):
        if lowered.endswith(suffix):
            url = url[: -len(suffix)].rstrip("/")
            break
    return url


def get_supabase_config():
    """Return {'url': ..., 'anon_key': ...}, empty strings when unset."""
    return {
        "url": normalize_url(os.environ.get("SUPABASE_URL", "")),
        "anon_key": os.environ.get("SUPABASE_ANON_KEY", "").strip(),
    }


def is_configured():
    """True only when both URL and anon key are present."""
    config = get_supabase_config()
    return bool(config["url"] and config["anon_key"])


def get_client():
    """Return an anon-key Supabase client.

    The anon key is safe for server-side use under Row Level
    Security; the service-role key must never reach the browser.
    Raises RuntimeError with setup instructions when unconfigured.
    """
    if not is_configured():
        raise RuntimeError(NOT_CONFIGURED)
    try:
        from supabase import create_client
    except ImportError as exc:
        raise RuntimeError(
            "The 'supabase' package is not installed. "
            "Run: pip install -r requirements.txt"
        ) from exc
    config = get_supabase_config()
    return create_client(config["url"], config["anon_key"])


def has_service_key():
    """True when a server-side service-role key is available."""
    return bool(os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip())


def get_service_client():
    """Return a service-role client for trusted server-side writes.

    Bypasses Row Level Security: use ONLY in server code paths that
    enforce authorization themselves (see src/notify.py). Never expose
    this client, its key, or its results to the browser. Raises
    RuntimeError when the key is absent; the message never includes
    the key value.
    """
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "Server-side writes are not configured. Set "
            "SUPABASE_SERVICE_ROLE_KEY in the server environment "
            "(never in the browser or in Git)."
        )
    try:
        from supabase import create_client
    except ImportError as exc:
        raise RuntimeError(
            "The 'supabase' package is not installed. "
            "Run: pip install -r requirements.txt"
        ) from exc
    return create_client(normalize_url(os.environ.get("SUPABASE_URL", "")),
                         key)
