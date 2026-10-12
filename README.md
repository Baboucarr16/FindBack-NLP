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
python app.py
```

Open `http://127.0.0.1:5000` (search), `http://127.0.0.1:5000/found`
(report a found item), `/register` and `/login` (need Supabase, see below).
With Supabase configured and `FINDBACK_STORE=supabase`, found reports
save persistently with owner binding, new found reports are
automatically matched (same 50/25/15/10 weights, TF-IDF text scorer),
and owners get duplicate-safe notifications under `/notifications`.
Claims live under `/claims` (claimant + report owner only).

First start downloads the `all-MiniLM-L6-v2` model (~90 MB) from
Hugging Face and caches it. Optional environment variables
(see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `PORT` / `HOST` | `5000` / `127.0.0.1` | Server bind address |
| `FLASK_DEBUG` | `1` | Set to `0` in production |
| `FLASK_SECRET_KEY` | dev-only key | Session signing; set a random value in production |
| `FINDBACK_MIN_SCORE` | unset (show all) | Hide candidates below this 0–1 score. Untuned: choose it with real labeled dev data only. |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` | unset (CSV mode) | Enable Supabase store + Auth |
| `FINDBACK_STORE` | `csv` | Set to `supabase` to use the persistent backend (needs above) |

## Supabase setup (needs a project + credentials)

1. Run `db/schema.sql` once in the Supabase SQL editor (see `db/README.md`),
   then review and run `db/migrations/002_match_notify_writes.sql` for
   automatic match persistence.
2. Copy `.env.example` to `.env` and fill in the keys. Never commit `.env`.
3. Validate the migration without writing anything: `python db/migrate_csv.py`
4. Import once: `python db/migrate_csv.py --execute` (reads the CSV only;
   skips already-migrated IDs, never modifies the file).

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
worker and a 120 s timeout for model load). Set `FLASK_DEBUG=0` and
`PORT` from the platform. Notes:

* CSV storage is a local file: platforms with ephemeral filesystems
  will lose new submissions on restart. Configure Supabase
  (`db/README.md`) for persistent storage.
* The Sentence-BERT model downloads (~90 MB) and loads into memory at
  startup; allow extra boot time and ~1 GB RAM.
* No secrets are used; do not add credentials to the repo.

Exact next steps depend on the chosen host (Render/Heroku/VPS) and
require account access, so deployment itself is left for the owner.
