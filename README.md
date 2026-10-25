# FindBack — NLP-Based Lost and Found Item Matching

Flask app that matches lost-item reports against found-item reports
using Sentence-BERT description similarity plus location, time, and
category context. Each candidate shows component-level evidence
("Why this match?"). Reports persist to `dataset/findback_reports.csv`
by default; Supabase PostgreSQL + Auth are supported when configured.

## Local setup (Windows PowerShell)

```powershell
cd C:\Users\babou\OneDrive\Desktop\FindBack
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:FINDBACK_STORE="csv"
python app.py
```

Open `http://127.0.0.1:5000` (search) or `/found` (report a found item).
The public account forms are not currently available; `/login` and `/register`
show a notice while authentication POST handlers remain for internal use.
With `FINDBACK_STORE=supabase`, users authenticate before submitting Lost or
Found reports. Both report types persist with owner binding. Search reads
active Found reports from Supabase and uses the existing Sentence-BERT
algorithm and weights. New Found reports also run the existing
automatic TF-IDF matcher against active Lost reports. Match pairs are
idempotent and owner notifications require the server-only service key.
Claims live under `/claims` (claimant + report owner only).

First start downloads the `all-MiniLM-L6-v2` model (~90 MB) from
Hugging Face and caches it. On this verified machine the model is cached and
the local search completed with Hugging Face offline mode enabled. Optional environment variables
(see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `PORT` / `HOST` | `5000` / `127.0.0.1` | Server bind address |
| `FLASK_DEBUG` | `1` | Set to `0` in production |
| `FLASK_SECRET_KEY` | dev-only key | Session signing; set a random value in production |
| `FLASK_COOKIE_SECURE` | automatic from `FLASK_DEBUG` | Set to `1` when serving over HTTPS |
| `FINDBACK_MIN_SCORE` | unset (show all) | Hide candidates below this 0–1 score. Untuned: choose it with real labeled dev data only. |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` | unset (CSV mode) | Enable Supabase store + Auth |
| `FINDBACK_STORE` | `csv` | Set to `supabase` to use the persistent backend (needs above) |

## Supabase setup (needs a project + credentials)

1. Run `db/schema.sql` on a disposable/test Supabase project, then review
   and validate `db/migrations/004_core_dataflow_security.sql` there.
   Do not assume migrations 002/003 were applied; 004 establishes the
   current policies whether or not those drafts ran. See `db/README.md`.
2. Copy `.env.example` to `.env` and fill in the keys. Never commit `.env`.
   Set a random `FLASK_SECRET_KEY`, `FLASK_DEBUG=0`, and HTTPS in
   production. Supabase Auth Site URL and redirect allowlist must match
   the app's email-confirmation destination.
3. Validate the CSV import without writing: `python db/migrate_csv.py`.
4. Import only after validating the target `SUPABASE_URL`:
   `python db/migrate_csv.py --execute` (CSV remains unchanged).

## Tests

```powershell
python -m pytest tests/ -q
```

Tests use temporary directories and stub the Sentence-BERT model, so
they never touch `dataset/findback_reports.csv` and need no network.

## Benchmark (real labels required)

```powershell
python src/check_leakage.py --dev-dir benchmark/dev --test-dir benchmark/heldout_test
python src/benchmark_evaluate.py --lost benchmark/dev/lost.csv --found benchmark/dev/found.csv --labels benchmark/dev/labels.csv --methods context,tfidf
```

> Real-world matching performance has not yet been established because
> a verified real labeled benchmark is unavailable. Numbers from the
> synthetic `dataset/findback_reports.csv` pairs are smoke tests only.

## Deployment

Production entry point is `wsgi.py` (`Procfile` runs gunicorn with one
worker and a 120 s request timeout). Set `FLASK_DEBUG=0` and
`PORT` from the platform. Notes:

* `GET /healthz` is a lightweight liveness endpoint; it reports only process
  availability and does not query Supabase, load the NLP model, or expose
  configuration details.

* CSV storage is a local file: platforms with ephemeral filesystems
  will lose new submissions on restart. Configure Supabase
  (`db/README.md`) for persistent storage.
* Supabase is not currently a safe public deployment mode: the SQL draft's
  active-report policy exposes Lost reports, and the public login/registration
  journey is unavailable. Do not deploy publicly in either mode until these
  privacy and product-mode decisions are resolved and tested.
* Startup does not load the Sentence-BERT model or read/index the CSV.
  The model is initialized once per worker on its first semantic-match
  request, and the CSV is read and encoded then; cached model and
  embeddings are reused until the CSV changes. The first matching
  request therefore takes longer and uses more memory than startup.
* The checked-in `Procfile` uses the existing `wsgi:application`
  entry point with one worker. Render services with a custom start
  command should use the same entry point and worker count.
* Auth tokens are kept in server process memory; the Flask cookie only
  carries an opaque session handle. Use one worker as configured: a
  multi-worker or multi-instance deployment needs a shared server-side
  session store before it can safely serve these sessions.
* No Google OAuth flow is implemented. It would require a separately
  enabled Supabase provider, provider credentials, callback route, and
  Site URL/redirect allowlist configuration.

Exact next steps depend on the chosen host (Render/Heroku/VPS) and
require account access, so deployment itself is left for the owner.
