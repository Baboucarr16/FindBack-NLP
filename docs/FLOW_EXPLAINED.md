# FindBack — How the Platform Works (Plain-Language Flow)

This document explains how FindBack works today, in simple language, and
names the exact file and function responsible for each step. It describes
what the code does. Anything marked **"intended but not yet verified
live"** was not proven against a running system in this session and must
not be presented as a working feature.

## The big picture

FindBack is a small Flask app with three layers:

```text
Browser (user)
   |
   v
Flask routes (app.py)          e.g. /search, /found, /claims, /notifications
   |
   v
Store (src/store.py)           CsvStore  OR  SupabaseStore
   |
   v
Matcher (src/semantic_matcher.py, src/matcher.py, src/auto_match.py)
   |
   v
Explanation + HTML (src/explain.py, templates/)
```

When a user submits a lost-item search, Flask builds a "lost report"
object, asks the matcher to score it against known found reports, then
renders the ranked results with an explanation for each candidate.

---

## Step 1 — Someone reports a lost item (`POST /search`)

1. The user fills the form on `templates/index.html` (item category,
   description, place, date, approximate time, …).
2. The form posts to `/search` (`app.py`, route `search`). A CSRF token is
   required on all state-changing posts (`app.before_request` /
   `protect_form_posts`).
3. Storage-mode checks run:
   - `FINDBACK_STORE` must be `csv` or `supabase` (otherwise an error page is
     shown).
   - If it is `supabase`, the Supabase backend must be configured, and the
     visitor must be logged in (`using_supabase()` + `current_user()`).
4. The required fields are validated (category, description, place, date,
   time).
5. The place/organization field is sanity-checked against the description
   (e.g. it must not just repeat the item text).
6. A `lost_report` dict is built (type `Lost`, status `Lost`, category,
   description, location fields, date, time).
7. Matching runs:
   - **CSV mode:** `find_semantic_matches_for_report` in
     `src/semantic_matcher.py` loads `dataset/findback_reports.csv`, encodes
     descriptions with Sentence-BERT, and ranks found rows.
   - **Supabase mode:** the lost report is first **saved** through
     `SupabaseStore.save_report` with the logged-in user's `owner_id` (and a
     submission idempotency key). Then `SupabaseStore.list_found` fetches
     active found reports, and `find_semantic_matches_against_reports`
     scores them with the same Sentence-BERT engine.
8. An optional weak-match filter may hide candidates:
   `FINDBACK_MIN_SCORE` (0.0–1.0, unset = show all). The cutoff is **untuned**.
9. For each candidate, `explain_match` (`src/explain.py`) builds a plain-language
   explanation (supporting / conflicting signals, per-component contributions).
10. `templates/results.html` renders the ranked candidates, each with the
    "Why this match?" panel, score bars, and a disclaimer that scores are
    similarity, **not** proof of ownership or a calibrated probability.

**Important:** in CSV mode the lost report itself is *transient* (it lives only
in the request) and in Supabase mode it is *persisted* with an owner and a
submission key.

---

## Step 2 — Someone reports a found item (`POST /found`)

1. The user opens `/found` (`app.py`, route `found`) and submits the found-item
   form.
2. Validation as in Step 1.
3. **CSV mode:** the app generates the next `FB###` report id and appends the
   row to `dataset/findback_reports.csv` (append-only). Success page shows the
   new `FB###` id.
4. **Supabase mode:** the app requires login, saves the found report through
   `SupabaseStore.save_report` with the user's `owner_id` and an idempotency
   key, then triggers the **automatic matching pipeline**
   (`src/auto_match.py`, `process_new_found_report`).
5. The automatic matcher:
   - fetches active lost reports (`store.list_active_lost`),
   - scores each lost report against the new found report (TF-IDF text
     similarity + location/time/category components),
   - for each lost report whose `final_score` is at or above the notify cutoff
     (`FINDBACK_NOTIFY_MIN_SCORE`, default **0.60**, explicitly untuned), persists
     a match pair (idempotent upsert on `lost_report_id + found_report_id`) and
     creates a notification for the lost report's owner.
   - the whole step is **best effort**: failures are counted, never raised into
     the user-facing success path.

---

## Step 3 — How the automatic match score is calculated (`src/auto_match.py`)

Reused weights (identical to the live search weights):

```text
final_score = semantic × 0.50 + location × 0.25 + time × 0.15 + category × 0.10
```

- **Semantic (description):** text similarity — Sentence-BERT cosine similarity
  for the `/search` path, TF-IDF cosine for the automatic matcher.
- **Location:** weighted overlap of place fields
  (place 0.30, campus 0.15, building 0.20, floor 0.10, area 0.25). Missing values
  on either side are skipped (not penalized). Partial/contained values get
  partial credit; similar strings get partial credit via similarity ratio.
- **Time:** proximity buckets (≤30 min → 1.0, ≤60 → 0.8, ≤120 → 0.5, ≤360 → 0.25,
  ≤1440 min → 0.1, else 0). Missing dates/times → 0.
- **Category:** 1.0 for an exact category match, else 0.

The result is a number between 0 and 1 that summarizes how similar two reports
are. It is a **similarity score**, not a probability.

---

## Step 4 — How a claim is filed (`/claims/new`)

1. Logged-in user opens the claim form for a found report.
2. The report must exist, be of type `Found`, and not belong to the claimant.
3. The claim is inserted with status `pending` (one active claim per user +
   report; duplicates raise a friendly error).
4. Only the report owner may approve/reject; transitions allowed are strictly
   `pending → approved|rejected` (claimant may withdraw).

---

## Step 5 — How notifications are delivered

- The inbox lives at `/notifications`; a user only ever sees their own rows
  (enforced by RLS + app queries).
- Automatic matches create notifications addressed to the **lost report's
  owner**, deduplicated by a stable key
  (`match:{found_report_id}:{lost_report_id}`).
- Writes are done by a **server-side trusted writer** (`src/notify.py`) using the
  Supabase **service-role** key. The recipient is re-derived server-side from the
  lost report's owner, both reports are re-verified before writing, and message
  text is built server-side. End-user clients cannot write cross-user
  notifications (least-privilege design).

---

## Step 6 — How authentication works

- Email/password via Supabase Auth (`src/auth.py`).
- On login, Supabase returns access/refresh tokens; they are kept in server-side
  process memory and mirrored into the Flask signed cookie only as an opaque
  session handle + display metadata.
- Every protected route checks the session (`login_required`, or explicit
  checks in `/found`, `/search`, claims, notifications in Supabase mode).
- Profile rows are created on demand (`ensure_profile`).

---

## Step 7 — CSV mode vs Supabase mode

| Concern | CSV mode | Supabase mode |
|---|---|---|
| Search (`/search`) | Public; transient lost report; Sentence-BERT over CSV | Login required; lost persisted owner-bound; found read from Supabase; Sentence-BERT; match pairs persisted; notifications sent |
| Found report (`/found`) | Appends `FB###` row to CSV | Login required; owner-bound insert; auto-match runs; pairs + notifications |
| Claims | Unavailable (friendly error) | Full lifecycle |
| Notifications | Unavailable (friendly error) | Full inbox |
| Persistence | Local file (append-only) | Supabase Postgres |

---

## End-to-end story (simple)

1. User A reports a lost phone (lost report).
2. User B reports the same phone as found (found report).
3. User B triggers automatic matching; a high-similarity pair is found, saved,
   and User A is notified.
4. User A opens the notification / claims page, files a claim on the found
   report.
5. User B reviews incoming claims and approves or rejects.
6. The UI stays honest: scores are described as similarity, not certainty.

---

## Where things live (quick map)

| Concern | File |
|---|---|
| Routes | `app.py` |
| Auth helpers | `src/auth.py` |
| Storage clients | `src/store.py`, `src/db_config.py` |
| Search matcher | `src/semantic_matcher.py` |
| Component matcher | `src/matcher.py` |
| Auto-match | `src/auto_match.py` |
| Explanations | `src/explain.py` |
| Notification writer | `src/notify.py` |
| DB schema / migrations | `db/schema.sql`, `db/migrations/` |
| Templates | `templates/` |

---

## Honest limitations (as of this writing)

- Live Supabase Auth, migrations, and end-to-end writes were **not** verified in
  the last session; see `docs/LOGIC_AUDIT.md` and
  `docs/PRODUCTION_READINESS_AUDIT.md`.
- Notification sending requires the server-side service-role key; without it the
  pipeline skips notifications by design.
- The notification threshold (`FINDBACK_NOTIFY_MIN_SCORE`) is a default, not tuned.
- Google login is planned for a later phase and is **not** implemented.

## Deployment safety note — 2026-10-25

The described Supabase end-to-end story is an architecture explanation, not a
verified public workflow. The SQL drafts currently permit anonymous reads of
all active reports, including Lost reports. The public credential forms are
absent, and standard Render filesystem writes would not make CSV submissions
durable. Do not deploy this flow publicly until the Lost-report policy, trusted
matching path, public Auth decision, and persistent storage have been reviewed
and tested in an isolated environment. Migration 004 remains unapplied.
