# FindBack — Logic and Security Audit

> **Historical audit snapshot:** The original audit below refers to an earlier checkout (`main` at `c267bdc`) and its test count. It is retained as a record of that review, not as the current branch/status. For the current integration worktree, see `PRODUCTION_READINESS_AUDIT.md`, `PROJECT_ARCHITECTURE.md`, and `OVERNIGHT_COMPLETION_REPORT.md`. Current SQL remains unexecuted; no production database was contacted in the overnight pass.

**Audit date:** 2026-10-25 (continued finalization pass)
**Branch context:** `main` at `c267bdc`, with uncommitted additive work on top
(including new `src/` modules, `db/`, `tests/`, `templates/`, docs).
**Scope:** Matching logic, storage modes, security posture, claims and
notifications. No migrations were applied, no data was changed, nothing was
committed or deployed.

---

## 1. How the audit was done

- Code reading of `app.py`, `src/auth.py`, `src/store.py`, `src/db_config.py`,
  `src/semantic_matcher.py`, `src/matcher.py`, `src/auto_match.py`,
  `src/explain.py`, `src/notify.py`, `db/schema.sql`, `db/migrations/*`,
  `templates/*`, `tests/*`.
- Full automated test run: **133 passed, 0 failed**
  (`python -m pytest tests/ -q --basetemp "C:/Users/babou/AppData/Local/Temp/opencode/pytest-tmp"`).
- Static SQL contract tests (`tests/test_migrations.py`,
  `tests/test_security_migration.py`) assert policy names, ownership scoping,
  and grants; these are assertions, **not** execution against a real database.
- Live Supabase verification: **not re-performed in this pass**; see
  *Unverified live state* below.

---

## 2. Verified behaviour vs. intended behaviour

### 2.1 Matching logic — verified in code

| Aspect | Verified behaviour |
|---|---|
| Weights | Final score = description×0.50 + location×0.25 + time×0.15 + category×0.10, in `src/matcher.py` (`find_matches`), `src/semantic_matcher.py` (`find_semantic_matches_against_reports`), and `src/auto_match.py` (`W_*`). `src/explain.py` mirrors the same weights. **No weight changes were made this pass** (no evaluation evidence supported retuning). |
| Description component | Sentence-BERT cosine similarity in the `/search` path; TF-IDF cosine in the automatic matcher; reported as similarity in [0, 1]. |
| Location component | Weighted field overlap (place 0.30, campus 0.15, building 0.20, floor 0.10, area 0.25). Missing value on either side → field skipped (no penalty). Containment → full credit; similarity ratio ≥0.80 → 0.75; ≥0.60 → 0.50. Final = matched weight / total weight. |
| Time component | Buckets: ≤30 min → 1.0, ≤60 → 0.8, ≤120 → 0.5, ≤360 → 0.25, ≤1440 min → 0.1, else 0. Missing → 0. |
| Category component | Exact (case-insensitive, trimmed) match → 1.0, else 0. Missing → 0. |
| Final score | Weighted sum of four components each in [0, 1] → final in [0, 1]. The UI and `explain.py` describe it as a weighted similarity, **not** a probability. |
| Ordering / truncation | Candidates sorted by `final_score` descending, top `top_n=5` (`head`). |
| Weak-match filter | `FINDBACK_MIN_SCORE` (unset = show all) applied **after** top-5 truncation — see gap in §6. |
| Honest presentation | Results page shows a disclaimer and per-candidate explanations with supporting/conflicting signals; scores shown as percentages. |

### 2.2 Automatic matching — verified in code

- Trigger: when a found report is saved in Supabase mode via `/found`
  (`app.py` → `process_new_found_report`), and when a lost report is saved via
  `/search` in Supabase mode.
- `src/auto_match.process_new_found_report(found_report, store, score_fn, min_score, notify_fn)`:
  - loads active lost reports;
  - scores each lost against the found (injectable `score_fn`, default TF-IDF);
  - for scores ≥ cutoff (default `FINDBACK_NOTIFY_MIN_SCORE = 0.60`, **untuned**),
    upserts a match pair and notifies the lost owner;
  - returns `{"matches", "notifications", "skipped", "errors"}` and never raises
    into the request path (best effort).
- Idempotency: match pairs upsert on `(lost_report_id, found_report_id)`;
  notifications dedupe via `dedupe_key = "match:{found}:{lost}"`.

### 2.3 Notifications — design resolved this pass

- **Problem:** an end-user client cannot safely insert a cross-user notification
  under least-privilege RLS (users may only write their own inbox).
- **Resolution (implemented, RLS untouched):** the Flask server is the trusted
  writer. `src/notify.py` (`get_notifier` / `notify_match_owner`) uses a
  service-role client and enforces:
  - recipient is re-derived server-side from the lost report's `owner_id`;
  - both reports are re-read and must exist; the lost report must still be
    `active` and owned as recorded;
  - message text is built server-side (no caller-supplied text);
  - dedupe key makes reprocessing idempotent (23505 → duplicate, not error).
- `auto_match.process_new_found_report` accepts `notify_fn` ∈ {`"store"`,
  callable, `None`}.
- `/found` wires `notify_fn=get_notifier()`; without a service key the notifier
  returns `None` → notifications skipped and counted, never failed loudly.

### 2.4 Auth, session, CSRF, errors — verified in code

- Email/password auth via Supabase; friendly error mapping
  (`friendly_auth_error`); no raw backend exceptions rendered to users.
- Sessions: opaque server-side session id; display metadata + tokens in server
  process memory; signed cookie holds opaque handle only. HttpOnly, SameSite
  Lax, Secure when `FLASK_DEBUG=0`; `FLASK_SECRET_KEY` required when
  `FLASK_DEBUG=0`.
- Logout: POST-only, clears local session and best-effort Supabase sign-out.
- CSRF: token required on POST/PUT/PATCH/DELETE for non-test requests; supplied
  via forms/context processor; logout/claims/register/login/search/found all
  include the token.
- Token refresh: `get_user_client` refreshes via `set_session` and mirrors
  rotated tokens into server memory.

### 2.5 Storage modes — verified in code

- CSV mode: anonymous, append-only found rows with `FB###` ids; lost reports
  transient; claims/notifications unavailable.
- Supabase mode: owner-bound writes, public read of active reports, owner reads
  of own rows, claims/notifications owner-scoped.

---

## 3. Unverified live state (honest limits)

- The Supabase project (`ukblzzpltlnvvutkdhir.supabase.co`) was reachable and
  read-only checks passed earlier, but **live authentication verification was
  blocked** by credential/email-confirmation state on the Supabase side.
- Migrations were **not** applied by us; live installed policy state is unknown.
  Current authoritative policy set is described by `db/schema.sql` + migration
  `004_core_dataflow_security.sql` (which supersedes drafts 002/003 by name).
- No live DB execution, no real token refresh against Supabase, no real
  notification insert was ever performed.
- Mocked tests only for auth/claims/notify/migrations; live behavior must be
  re-verified before production demo reliance.

---

## 4. Findings and prioritized recommended fixes

### P0 — must resolve before live demo / production use

1. **Live prerequisite chain (owner action):** apply reviewed migration
   `004_core_dataflow_security.sql` (or the tightened `002` as appropriate) on the
   target Supabase project; confirm/test two Auth users with known passwords;
   set server-only `SUPABASE_SERVICE_ROLE_KEY`; set `FLASK_SECRET_KEY` and
   `FLASK_DEBUG=0`; enable HTTPS. Without these, live verification cannot run.
2. **Live end-to-end verification:** login → profile → report lost → report
   found → auto-match → persisted pair → notification → claim → owner decision →
   cross-user isolation.

### P1 — product correctness

3. **Tune the notification threshold** `FINDBACK_NOTIFY_MIN_SCORE` (default 0.60)
   using real labeled development data; it is explicitly untuned.
4. **Semantic engine consistency:** automatic matching uses TF-IDF while the
   primary search uses Sentence-BERT. Decide whether to unify or document the
   divergence.

### P2 — robustness

5. **Weak-match filter ordering:** apply `FINDBACK_MIN_SCORE` before top-5
   truncation so filtering cannot hide better candidates beyond rank 5.
6. **Session store:** move auth token/session state to a shared store before any
   multi-worker deployment.

### Already delivered as minimal, well-tested corrections (this branch)

- Server-side service-role notification writer (`src/notify.py`) with
  re-derived recipient + re-verification; key never logged/returned; no RLS
  loosening.
- Auto-match `notify_fn` abstraction + `skipped` counter; `/found` wiring.
- Tightened migration 002 (owner-of-pair insert check, fail-closed) and kept
  owner-only notification insert; drift tests updated.
- New tests: `tests/test_notify.py`, auto-match notify-path tests, migration drift
  strengthening.

---

## 5. Final integrity status at last full run

- Tests: **133 passed, 0 failed** (mocked Supabase/NLP; no live calls).
- `dataset/` and `benchmark/` untouched (`git diff --quiet` clean).
- Frontend redesign preserved (additive only).
- No commit/push/deploy/migration applied without approval.

---

## 6. Next recommended step

The recommendation above is a historical snapshot and is superseded by the
current safe plan below. Do not treat the old “apply migration” wording as an
authorization or instruction to modify a live project.

## Current authoritative status — 2026-10-25

- No production Supabase project was contacted in this final pass. Migration
  004 remains unapplied. The prepared active-report SELECT policy still exposes
  active Lost reports; it must be redesigned and tested in an isolated
  database before any live use.
- Public login/registration UI remains intentionally absent. Backend Auth,
  claims, notifications, and database policies remain unverified end to end.
- Local CSV demo remains the supported demonstration path. The interface now
  labels the checked-in examples as synthetic. Search remains transient; found
  submission appends to the CSV, so do not submit against the checked-in file.
- Two homepage `100vw` decorative pseudo-elements were replaced with
  section-bounded sizing. A regression test covers this source-level risk, but
  browser rendering at mobile/desktop widths remains unverified.
- Baseline suite: **156 passed**. Current full suite:
  `python -m pytest tests/ -q --basetemp=.pytest-master-final3` — **159 passed**.
  No test executes the SQL against PostgreSQL.
- Next safe work: resolve Lost-report privacy with a trusted server matching
  design, execute ordered migrations and RLS tests only in a disposable/local
  database, restore an intentional public Auth journey only if required, and
  perform real-browser responsive/accessibility checks. Production changes
  require separate review and explicit authorization.

## Deployment publication audit — 2026-10-25

- Added `/healthz` as a generic liveness response; it passed a route regression
  test and does not touch Supabase or model state.
- Full suite: **160 passed in 7.60s**; `pip check` found no broken requirement
  metadata; WSGI import passed with debug disabled and a throwaway local key.
- `db/schema.sql`, migration 004, and `db/README.md` now prominently warn that
  the current active-report policy exposes Lost reports and must not be used
  for a public/shared deployment.
- The connected Render workspace has no FindBack service and is unrelated to
  this GitHub repository. A public Render deployment was not created.
