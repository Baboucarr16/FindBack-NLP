"""Production WSGI entry point for FindBack.

Used by gunicorn / Render / Heroku (see Procfile).
Debug is always off here; local development uses `python app.py`.
"""

import os

os.environ.setdefault("FLASK_DEBUG", "0")

from app import app  # noqa: E402

application = app
