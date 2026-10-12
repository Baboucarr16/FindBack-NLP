"""Environment/secret-hygiene tests (local only, no network)."""

import os

import tests.conftest  # noqa: F401  (path setup)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Every variable the code reads must be documented in .env.example.
CODE_READ_VARS = {
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "FLASK_SECRET_KEY",
    "FLASK_DEBUG",
    "FINDBACK_MIN_SCORE",
    "FINDBACK_STORE",
    "HOST",
    "PORT",
}


def _example_keys():
    keys = set()
    with open(os.path.join(ROOT, ".env.example"), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip().lstrip("#").strip()
            if line and not line.startswith("#") and "=" in line:
                keys.add(line.split("=", 1)[0].strip())
    return keys


def test_env_example_documents_all_code_vars():
    assert CODE_READ_VARS <= _example_keys()


def test_env_example_contains_no_real_secrets():
    with open(os.path.join(ROOT, ".env.example"), encoding="utf-8") as fh:
        content = fh.read()
    assert "eyJ" not in content  # no JWT material
    assert "sb_secret" not in content
    assert "change-me" in content  # placeholder secret key


def test_dotenv_file_is_gitignored():
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as fh:
        ignored = [line.strip() for line in fh]
    assert ".env" in ignored
