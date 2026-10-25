# FindBack Production Readiness Audit — Phase 1

**Audit date:** 2026-10-25<br>
**Branch:** `audit/production-readiness`<br>
**Scope:** Local repository and tests only. No Supabase connection, database query, migration, configuration change, or deployment was performed. Live-project facts below are only those supplied in the audit request.

## Executive summary

**Readiness: Not production ready for the Supabase-backed workflow.** The default application is CSV-backed. The configured Supabase path persists authenticated found reports, claims, and some match/notification data, but the user-facing lost-item search still reads the CSV matching engine. Supabase report retrieval is not wired into that search, and there is no user-facing lost-report persistence path. Consequently, the main matching workflow is split across stores and new Supabase found reports are not available to normal searches.

Authentication uses Supabase email/password calls and Flask’s signed cookie session. It has no Google OAuth path, no token refresh persistence, and profile creation failures are silently ignored. Local tests pass, but they stub external services and do not establish that the production Supabase schema permits the configured writes. In particular, the supplied live-state description says there are no recorded migrations; the checked-in base schema alone does not grant the insert/update policies required by automatic match persistence.

No application fixes were made in Phase 1. The only added file is this audit report. The worktree’s pre-existing untracked `.pytest_tmp/` directory was left untouched.

## Findings

### High — Supabase reports are not used by the normal search path

`app.py:455` calls `find_semantic_matches_for_report(lost_report, top_n=5)` without consulting `SupabaseStore`. The matcher is backed by the CSV dataset. `app.py:665-704` saves found reports to Supabase when `using_supabase()` is true, and `src/store.py:83-111` provides Supabase report read/write methods, but those reads are not part of the search request. The `/search` handler also constructs an ephemeral `USER_REPORT`; it does not save the lost report. Thus Supabase found submissions are absent from normal search results, while the automatic matcher has no route-created lost reports to compare against unless data was imported separately.

**Impact:** The configured persistent mode does not provide an end-to-end persistent lost-and-found matching flow. Automatic matching can run against imported active lost reports (`src/auto_match.py`), but that is separate from the public search experience.

### High — Base RLS policies expose profile data and all match scores

In `db/schema.sql:150-152`, `profiles_read` uses `USING (true)`, so any role with table access can read every profile row, including the non-null `email` column (`db/schema.sql:13-18`). At `db/schema.sql:178-180`, `match_results_read` also uses `USING (true)`, exposing report-pair IDs and component/final scores without ownership filtering. RLS is enabled, but these policies still grant broad row visibility. The supplied live-state description confirms RLS is enabled on all five tables; it does not establish which local policy drafts are installed, and no live policy inspection was made.

**Impact:** Public profile email disclosure and match-result exposure are inconsistent with private account/match data. Review and replace these policies with the intended visibility model before production use.

### High — Claim RLS is weaker than the application route checks

The web flow checks that a claim targets a Found report and is not the report owner (`app.py:1180-1230`). The database insert policy at `db/schema.sql:192-194` checks only `auth.uid() = claimant_id`; it does not enforce report type, active status, or non-ownership for direct Data API calls. The base update policy at `db/schema.sql:196-204` permits either claimant or report owner to update and has no `WITH CHECK`, so it does not constrain changed claimant/report linkage or status. The draft `003_security_and_idempotency.sql:10-31` narrows decisions to the report owner and grants only status updates, but it is explicitly a draft and the supplied project has no migration history.

**Impact:** Route validation is bypassable through direct authenticated API calls if the base schema is installed. Claim lifecycle protections depend on whether draft migration 003 is reviewed and applied.

### High — Supabase errors are rendered directly to users

The `/found` exception handler interpolates the caught backend exception into HTML (`app.py:706-715`). Claim setup, list, create, decision, and notification error handlers similarly include exception text (`app.py:1099-1107`, `1136-1145`, `1256-1263`, `1313-1320`, `1359-1368`). Provider/database errors can expose schema names, policy details, or query context. This is not evidence that credentials are currently printed, but it is an avoidable information disclosure path. No exception strings were captured during this audit.

### High — Authentication session is not refreshed or revoked at Supabase

`src/auth.py:109-117` stores access and refresh tokens in Flask’s client-side signed session cookie. `get_user_client()` (`src/auth.py:88-100`) calls `set_session` from those saved values, but does not persist any rotated/refreshed tokens back into Flask session. `logout_session()` only removes the local cookie value (`src/auth.py:120-123`); it does not call Supabase sign-out/revoke. Protected routes check only whether a session dictionary has an ID (`src/auth.py:125-141`). A token that expires or is revoked can therefore leave a seemingly logged-in browser, with database calls failing later; logout does not revoke the Supabase session. No Google OAuth implementation or callback route was found; signup/login call only email/password methods (`src/auth.py:67-85`).

**Impact:** Reliability degrades after token expiry/rotation; logout is local-only. Use HTTPS and a strong `FLASK_SECRET_KEY` as documented, and implement/verify refresh and sign-out behavior before relying on long-lived sessions.

### High — Supabase write policies required by the app are in unapplied migration drafts

The base schema defines only a SELECT policy on `match_results` (`db/schema.sql:178-180`) and only SELECT/UPDATE policies on notifications (`db/schema.sql:207-212`). `src/auto_match.py` upserts match results and `src/notify.py` inserts cross-user notifications. `002_match_notify_writes.sql` adds match inserts and own-notification inserts, but service-role notifications bypass RLS. The README instructs running 002, while migration 003 says it must follow 002 and is a review draft. Given the user-supplied fact that the live project has no recorded migrations, none of these additions should be assumed active.

**Impact:** Depending on the actual installed policies and privileges, normal match writes can be denied; best-effort matching suppresses errors and `/found` still reports success. The existing code does not make deployment readiness apparent to operators.

### Medium — Login may succeed without a required profile row

Both registration and login call `ensure_profile()` in a broad exception handler and silently continue (`app.py:946-956`, `1040-1050`). Reports reference `profiles(id)` (`db/schema.sql:26-27`), and report inserts use the logged-in user as `owner_id` (`app.py:690-704`). If profile upsert fails due to schema, policy, or network problems, the user sees a successful login but subsequent report creation may fail at the foreign key or RLS layer.

### Medium — Schema and migration drafts have material behavior differences

See the comparison below. Especially consequential are claim-update hardening, the notification dedupe window, and the `match_results` upsert update policy/privilege in migration 003. Those differences are not applied merely because the SQL files exist.

### Medium — CSRF protection is absent on state-changing Flask routes

No CSRF extension/token validation is present in `requirements.txt` or the route handlers. State-changing routes include report submission, claim filing, and claim decisions (`app.py:548-550`, `1153-1157`, `1270-1275`); logout is a state-changing GET (`app.py:1058-1065`). Flask’s default session cookie settings mitigate some cross-site requests but do not replace explicit CSRF defenses, especially for GET logout and authenticated POSTs.

### Low — Supabase mode selection can silently fall back to CSV

`using_supabase()` requires both `FINDBACK_STORE=supabase` and configured URL/key (`app.py:73-83`). `get_store()` uses the same requested-and-configured condition and otherwise returns `CsvStore` (`src/store.py:231-238`). A typo or missing environment value can therefore make report creation use local CSV without an explicit startup failure. `.env.example` documents the CSV default and opt-in variable.

## Storage and matching data flow

| Operation | CSV mode | Supabase mode |
|---|---|---|
| User search (`POST /search`) | Calls existing Sentence-BERT matcher over `dataset/findback_reports.csv`. Lost query is transient. | Same CSV matcher and transient lost query; does not read Supabase reports. |
| Found report (`POST /found`) | Appends a row to CSV and displays the generated `FB...` ID. | Requires session; inserts a report through the user-scoped Supabase client, then attempts automatic matching. |
| Automatic matching | Not invoked by the standard CSV submission path. | `process_new_found_report` reads active Lost rows from Supabase and upserts pairs; it cannot see a lost report submitted through `/search` because that request is not persisted. |
| Claims / notifications | Not available as persistent features. | Authenticated routes query/write via user-scoped clients; cross-user match notices use the service-role writer when configured. |
| Report retrieval | Search engine reads CSV. | `SupabaseStore.list_found/get_report` exist, but `list_found` is not used by `/search`. |

The `db/migrate_csv.py` tool is dry-run by default and only reads CSV in both modes. Its `--execute` mode does perform database inserts using the service-role key; it was not run.

## Authentication and authorization trace

- **Signup:** `/register` validates basic email shape and six-character minimum; calls `auth.sign_up`; does not create a session before email confirmation. If confirmed immediately, it stores the session and best-effort upserts the profile.
- **Login:** `/login` calls `sign_in_with_password`, stores the returned access/refresh tokens in the Flask session, and best-effort upserts the profile.
- **Logout:** `/logout` is GET and clears only the Flask session.
- **Protected routes:** claims and notifications use `@login_required`; `/found` checks login only in Supabase mode. `/search` remains public and transient.
- **Ownership enforcement:** application stores use user-scoped Supabase clients; report writes attach `owner_id`; claim decision checks the report owner in Python and is also intended to be restricted by migration 003. Database RLS remains the security boundary for direct API requests and must be fixed independently of route checks.
- **Google OAuth:** No OAuth sign-in call, route, callback, or template control was found. It is not implemented.
- **Redirect/configuration:** Signup does not pass a redirect URL to Supabase. If email confirmation is enabled, configure the Supabase Auth Site URL and allowed redirect URLs for the actual app origin in Supabase dashboard/Auth settings, and decide where confirmation links should land. No live Auth setting was inspected or changed. There is no app callback route today.
- **Secrets:** `.env` is ignored by `.gitignore`; `.env.example` contains placeholders and documents that service-role credentials stay server-side. `src/db_config.py` does not include key values in its configuration errors. No `.env` contents were opened or printed. Service-role clients are used only in `src/notify.py` and the explicit migration executor by repository search. User-facing raw exception rendering remains a separate disclosure concern.

## Local schema versus migration drafts

Only `db/migrations/002_match_notify_writes.sql` and `003_security_and_idempotency.sql` exist in the repository. The user supplied that the live project has five tables, RLS enabled on each, zero rows, and no recorded migrations. The audit did not connect to Supabase; whether the base schema or manual policy changes currently exist is unknown.

| Area | `db/schema.sql` | Migration 002 | Migration 003 |
|---|---|---|---|
| Match-result writes | SELECT policy only; no insert/update policy. | Adds insert policy requiring caller owns either report in the pair. | Adds owner-of-either-side update policy and table UPDATE grant for upsert conflict handling. |
| Notifications | SELECT and owner UPDATE policies; no insert policy. | Adds insert-own policy. | Does not change notification insert policy. Cross-user notification remains service-role-only. |
| Claim update | Claimant or report owner can update; no `WITH CHECK`; table policy does not limit columns. | No change. | Replaces with report-owner-only `USING` and `WITH CHECK`; revokes broad update and grants only `status` column to authenticated. |
| Notification dedupe | Partial unique `(user_id, dedupe_key)` only while unread. | No change. | Creates all-time unique key (when non-null), drops/replaces prior index; makes read notifications permanent dedupe records. |
| Claim uniqueness | Unique `(report_id, claimant_id)` forever. | No change. | No change. This is stricter than README's “one active claim” wording and does not permit a later claim after a withdrawn/rejected claim. |
| Idempotency | Tables/indexes mostly use `IF NOT EXISTS`; policies use drop/create; trigger is dropped/recreated. Existing table definitions are not reconciled by `CREATE TABLE IF NOT EXISTS`. | Policy replacement is repeatable in intent but is not wrapped in a transaction. | Explicit transaction; index/policy/grant operations are intended to be repeatable, subject to permissions and actual pre-existing state. |

Additional schema observations:

- All five tables enable RLS in `db/schema.sql:140-148`; that fact alone does not make access private, as the public `profiles_read` and `match_results_read` policies demonstrate.
- Foreign keys: profiles to `auth.users` cascade; reports to profiles set owner null on profile deletion; match results and claims cascade with reports; claims cascade with profiles; notifications cascade with profile and set related report null on report deletion.
- Nullable columns are deliberate in several places: report `owner_id`, event date/time, legacy ID; match scores are non-null with defaults; claim decision timestamp and notification dedupe/related report are nullable. `owner_id` nullable supports imported legacy rows but means those reports have no owner for claims/notifications.
- Checks constrain report type/status, claim status, notification kind, and prevent matching a report to itself. There is no database check that `lost_report_id` references a Lost report and `found_report_id` a Found report.
- Indexes cover report owner/type-status, match lost-report/final-score, claim report/claimant, notifications user/read/date, plus unique constraints. No separate found-report match index is defined.
- `CREATE TABLE IF NOT EXISTS` does not update an already-existing table to match this file. The README's “run once” instruction does not make later schema drift safe or self-healing.

## Test commands and results

Command run from repository root:

```text
python -m pytest tests/ -q
119 passed in 20.55s
```

The suite uses fakes/stubs and temporary filesystem paths for Supabase and NLP-dependent paths. It does not contact Supabase or verify the live schema, Auth redirect settings, RLS execution, or real token refresh behavior. No test was added because no implementation change was made in this audit-only phase.

## Prioritized remediation plan

1. **Agree on the persistent product flow:** decide whether lost reports should be stored in Supabase. If yes, persist authenticated lost submissions and make the search query active Supabase found reports (preserving scoring); define how anonymous search should behave. Ensure owner IDs and profile creation are reliable.
2. **Review RLS before use:** limit profile reads to self or remove public email exposure; scope match-result reads to report owners/claim participants or expose a deliberately safe view; strengthen claim insert/update constraints at the database layer. Treat migrations 002/003 as drafts until reviewed against a local/test Supabase project.
3. **Make auth lifecycle robust:** persist token refresh/rotation correctly, revoke Supabase sessions on logout, fail visibly and safely when profile creation fails, and decide email-confirmation redirect URLs. Add Google OAuth only if required.
4. **Stop rendering raw backend exceptions:** return generic user messages and send sanitized, secret-free diagnostic details to server logs with request correlation.
5. **Add CSRF protection and make logout POST-only.**
6. **Validate migration drafts on a disposable Supabase project:** compare installed schema/policies/grants to the reviewed SQL, run integration checks under anon/authenticated/service-role contexts, and prepare separate SQL for human review. Do not apply to production as part of this phase.
7. **Make backend selection fail loudly in production:** detect `FINDBACK_STORE=supabase` with missing configuration instead of silently falling back to CSV; expose a safe startup health/config status.

## Changes made on this branch

- Added `docs/PRODUCTION_READINESS_AUDIT.md`.
- No code, SQL migration, production configuration, or data changes.
- Branch: `audit/production-readiness`; not merged or deployed.

## Phase 2 implementation status

### Data flow

- `FINDBACK_STORE=supabase` now controls both report flows. Lost searches
  require login, save an owner-bound Lost row, fetch active Found rows
  from Supabase, and pass them through the existing Sentence-BERT
  scorer, component weights, and explanation builder. The same request
  persists the resulting match pairs. CSV mode still uses the CSV
  matcher and existing append flow.
- Found submissions remain owner-bound in Supabase and now carry a
  unique submission key. Repeated submissions with the same key return
  the existing owner row. Match pairs use the existing unique pair key;
  notification dedupe is permanent, including after a notification is
  read.
- Selecting Supabase without credentials or selecting an invalid store
  value now returns a safe configuration error instead of falling back
  to CSV. CSV retries still use the existing append-only format; the
  report idempotency guarantee added here is for the Supabase path.

### Security and authentication

- Active reports remain readable for search. Profile rows are visible
  only to their user; match results are visible only to a participant
  who owns one side. Report writes require the authenticated owner.
- Claims can only be inserted by the claimant as `pending`, against an
  active Found report owned by another user. Owners alone can approve or
  reject; claimants may only withdraw. SQL column grants prevent callers
  changing ownership/linkage fields. Closed/rejected claims may be
  re-filed, while only one pending/approved claim per user/report pair
  can exist.
- Auth tokens are held in server process memory. Browser cookies hold
  only the signed opaque session handle and non-secret display metadata.
  Expired/invalid refresh sessions clear the local login; rotated tokens
  update server-side state. Logout requests local Supabase sign-out and
  always clears the local session. Cookies are HttpOnly and SameSite
  Lax, Secure by default when `FLASK_DEBUG=0`; production startup rejects
  the development/placeholder secret. Logout is POST-only and every
  state-changing form carries a CSRF token.
- User-facing backend errors are now generic. Provider authentication
  errors use the existing friendly-message mapper; database errors and
  SQL details are not rendered.
- Google OAuth remains out of scope. Later setup requires enabling the
  provider and credentials in Supabase Auth, implementing the Flask
  callback/return route, and configuring the Site URL and redirect
  allowlist. Email confirmation also needs those URL settings.

### SQL prepared

- `db/schema.sql` now represents the restrictive clean-install policy
  model and report submission key.
- Added ordered `db/migrations/004_core_dataflow_security.sql`. It does
  not depend on migration drafts 002/003; it replaces their policy names
  and grants, adds report idempotency, adjusts claim uniqueness, and
  changes notification dedupe to all-time. Rollback considerations are
  recorded in the file. Neither schema nor migration was executed.
- `db/README.md` and root `README.md` describe the current data flow,
  local/test-first SQL order, Supabase/Auth redirect setup, one-worker
  session constraint, and the separate Google OAuth work.

### Remaining risks and verification limits

- No local Supabase/Postgres database was available. Docker is installed
  but its local engine pipe is not running; Supabase CLI and `psql` are
  unavailable. SQL policy execution, role grants, migration reruns, and
  index creation against existing data remain unverified. Static SQL
  assertions are not a substitute for an isolated database run.
- The supplied production project was not contacted. Its live policy
  state remains unknown; do not apply migration 004 until it is reviewed
  and tested on an isolated project and then separately approved.
- Server-side token storage is process-local and matches the checked-in
  single-worker Gunicorn configuration. Multi-worker/multi-instance
  hosting needs a shared server-side session store. Restarting the app
  clears active logins.
- CSV mode remains anonymous and append-only, so client retries can
  duplicate CSV submissions. This phase adds durable idempotency to the
  Supabase-backed flow without changing the existing CSV file format.
- If `SUPABASE_SERVICE_ROLE_KEY` is absent, pair rows still persist but
  cross-user notifications are skipped by design. The service key must
  remain server-only.
- Email confirmation redirects and provider allowlists have not been
  verified against a project. Google OAuth is not implemented.

### Phase 2 files changed

- `app.py`, `src/auth.py`, `src/store.py`, `src/semantic_matcher.py`,
  `src/notify.py`
- `db/schema.sql`, `db/migrations/004_core_dataflow_security.sql`,
  `db/README.md`, `README.md`, `.env.example`
- `templates/index.html`, `templates/found.html`, `templates/login.html`,
  `templates/register.html`, `templates/claim_form.html`,
  `templates/claims.html`, `static/style.css`
- Tests updated/added under `tests/` for Supabase data flow, storage
  idempotency, matching weights, auth/session rotation and logout,
  notification recipient verification, CSRF, and SQL policy contracts.

### Verification results

- Ran `python -m pytest tests/ -q`: **133 passed in 8.81s**.
- This suite uses Flask's test client and mocked Supabase clients. It
  verifies request behavior, ownership checks, idempotency logic, and
  static SQL contracts; it does not execute PostgreSQL policies or the
  migration engine.
- No isolated Supabase/Postgres test database was available, so migration
  application, RLS behavior under real Supabase roles, and query behavior
  against Postgres remain unverified. Docker's local engine was not
  running, and Supabase CLI/`psql` were unavailable.
- No production Supabase connection, configuration change, migration,
  deploy, merge, or production data operation was performed.

## Milestone C - local UI and evaluation update

### Changes made

- Added a shared light/dark theme control in `templates/base.html` and
  `static/theme.js`. The first visit follows `prefers-color-scheme`; an
  explicit choice is saved under the non-sensitive `findback-theme`
  local-storage key. System changes continue to apply until the visitor
  chooses a theme. The early-loading local script sets the theme before
  the stylesheet is applied to reduce a flash of the wrong palette.
- Added dark palette tokens for page surfaces, form controls, result
  cards, alerts, status markers, the search workspace, and the home-page
  illustration in `static/style.css` and `templates/index.html`.
- Added an accessible progress message to the search form. Submitting
  with JavaScript announces comparison progress and disables the submit
  button to reduce accidental repeat submissions. Server-side validation,
  error alerts, and the existing empty-results state remain in place.
- Changed the results heading from `4 SIGNALS` to `4 WEIGHTED
  COMPONENTS`; the displayed breakdown is the four existing score
  components (description, location, time, and category). Matching
  behavior, weights, and report fields were not changed.
- Added `tests/test_theme.py` for theme assets, toggle markup, loading
  status, and validation alert contracts.

### Benchmark and Gemini status

- `benchmark/dev/` has one placeholder lost report, two placeholder
  found reports, and one placeholder label. `benchmark/heldout_test/`
  has one placeholder row in each CSV. The evaluator removes example
  labels and reports that nothing was scored. Leakage checking also
  reports no real reports to compare. These are not usable real-world
  evaluation sets.
- `dataset/evaluation_results.csv` and
  `dataset/model_comparison_results.csv` each contain 12 synthetic
  examples; `README.md` explicitly says the synthetic rows are smoke
  tests only. No verified human-labeled benchmark is available.
- No Gemini experiment was run and no API credentials were read. The
  live API call remains unapproved. Before a comparison, collect
  consented, anonymized development examples with verified outcomes;
  preserve the held-out split; compare the existing description scorer
  with Gemini embeddings on the same dev queries and report Top-1,
  Top-3, MRR, request latency, and estimated cost. Do not send names,
  contact details, or unnecessary report fields. Keep the existing
  matcher as the fallback and do not tune against held-out results.

### Milestone C verification and limits

- Baseline before UI changes: `python -m pytest tests/ -q
  --basetemp=.pytest-milestone-c-baseline` - **136 passed in 19.55s**.
- Focused after UI changes:
  `python -m pytest tests/test_theme.py tests/test_ui_templates.py -q
  --basetemp=.pytest-milestone-c-focused2` - **9 passed**.
- Full suite after all changes: `python -m pytest tests/ -q
  --basetemp=<isolated-temp-dir>` - **142 passed in 7.46s**.
- `git diff --check` completed successfully (Git emitted only existing
  Windows LF/CRLF working-copy notices).
- Evaluator smoke check:
  `python src/benchmark_evaluate.py --lost benchmark/dev/lost.csv
  --found benchmark/dev/found.csv --labels benchmark/dev/labels.csv
  --methods context,tfidf` - no evaluable rows; no metrics produced.
- Leakage smoke check:
  `python src/check_leakage.py --dev-dir benchmark/dev
  --test-dir benchmark/heldout_test` - no real reports to compare.
- Presentation-path smoke check used `FINDBACK_STORE=csv`, blank Supabase
  URL/keys, and Hugging Face/Transformers offline mode. The locally cached
  Sentence-BERT model loaded without network access; the known search returned
  HTTP 200 with synthetic candidate `FB002` and the ownership disclaimer.
  A found report saved as `FB027` in a temporary copy, and a follow-up search
  returned it. The original dataset was not used for writes. Login and
  registration each returned HTTP 200 with the authentication-not-configured
  warning under this explicit CSV configuration.
- Started `python app.py` bound to `127.0.0.1` with debug disabled, a
  throwaway local Flask secret, CSV mode, blank Supabase settings, and
  offline model loading. HTTP GETs to `/`, `/found`, `/login`, and
  `/register` all returned **200**; login/register displayed the
  configuration warning. The local server was stopped after the check.
- No browser runtime was available (Chrome/Edge/Chromium, Chrome DevTools,
  and Node.js were not available). The new interaction was checked by
  code and Flask/static-asset tests, but theme rendering, mobile layout,
  keyboard behavior, browser console output, and actual storage
  persistence remain unverified in a browser.
- The three protected CSV files were hashed before and after the changes;
  their SHA-256 hashes are unchanged:
  `findback_reports.csv`:
  `4eac24c4fdc18499f4509bd715b7cad48f9910842afcdc26dbdfcecc27680429`;
  `evaluation_results.csv`:
  `ba19a6efe4fe5cf0079bc2f7a471da15413e80a8755c7647c8058b7144b74b23`;
  `model_comparison_results.csv`:
  `e8d2ad8c634b8bd518e565ec2e04433567c8c3e1421bea4928263a09e4dcb46a`.
- No local Supabase/Postgres environment was available. The backend
  authentication, RLS, notification, and migration limitations in the
  Phase 2 section still apply; SQL remains unapplied and production was
  not contacted.

## Premium editorial UI and public authentication UI removal

### Changes made

- Updated the shared shell navigation to expose only Search, found-item
  reporting, the search call to action, and the theme control. The conditional
  account links and logout form were removed for both anonymous and authenticated
  sessions; the protected routes and their authorization checks were left intact.
- Replaced the public login and registration forms with a recovery-desk notice.
  The notice remains truthful when Auth is not configured, and the Flask route
  handlers still exist. The route pages no longer render email/password inputs,
  account links, or submit controls.
- Shifted the shared palette to warm paper, forest ink, clay accents, and a
  muted field-note marker. Added a serif italic headline accent, refined borders
  and report cards, and styled the direct-access notice in both themes.
- Kept the existing system-preference theme selection, local preference storage,
  pre-stylesheet theme script, search progress feedback, report field names,
  CSRF inputs, submission keys, and matching output behavior.
- Updated the demo runbook so it no longer presents the Supabase account,
  notification, or claim workflow as a supported live demo.

### Verification

- Pre-change baseline in this worktree: `python -m pytest tests/ -q
  --basetemp=.pytest-premium-baseline` — **142 passed in 10.23s**.
- Focused UI/auth checks after the first implementation: **34 passed**.
- Final full suite after all code changes: `python -m pytest tests/ -q
  --basetemp=.pytest-premium-final` — **146 passed in 7.81s**.
- Regression tests assert that neither anonymous nor authenticated public
  navigation advertises account pages, and that direct account routes render no
  public credential forms while retaining their configuration warning.
- Browser screenshot/runtime verification remains unavailable in this
  environment. Mobile and light/dark rendering were reviewed in CSS and template
  contracts only; actual browser layout, contrast rendering, and console output
  remain unverified.
- `git diff --check` completed successfully; Git printed only working-copy
  LF/CRLF conversion notices for pre-existing files. A recursive template search
  found no login/register links or logout controls.
- Protected CSV SHA-256 values still match the recorded baseline:
  `findback_reports.csv` —
  `4eac24c4fdc18499f4509bd715b7cad48f9910842afcdc26dbdfcecc27680429`;
  `evaluation_results.csv` —
  `ba19a6efe4fe5cf0079bc2f7a471da15413e80a8755c7647c8058b7144b74b23`;
  `model_comparison_results.csv` —
  `e8d2ad8c634b8bd518e565ec2e04433567c8c3e1421bea4928263a09e4dcb46a`.
- SQL was not applied; no Supabase project, production credentials, external
  services, or protected CSV dataset contents were used for this UI work.

### Readiness estimate after Milestone C

- Local demonstration readiness: **7/10**. The app has a cohesive shared
  shell, responsive existing layouts, a system-aware theme, search
  progress feedback, and clearer candidate evidence. A browser visual
  pass is still outstanding.
- Production readiness: **3/10**. Automated tests and code-level checks
  do not verify live Supabase Auth, RLS behavior, PostgreSQL migration
  execution, deployment settings, or end-to-end notification delivery.
  Real-world matching quality is also unmeasured.

## Current final-master status — 2026-10-25

This file contains Phase 1 and later milestone snapshots. The latest local
verification is documented in `OVERNIGHT_COMPLETION_REPORT.md` and supersedes
older counts/status above:

- Pre-pass baseline: **156 passed**. Current suite:
  `python -m pytest tests/ -q --basetemp=.pytest-master-final3` — **159 passed**.
- The local CSV UI labels the checked-in synthetic examples on homepage and
  results; the hero background/divider pseudo-elements no longer use `100vw`.
- HTTP checks on the local server at `127.0.0.1:5187` and a CSRF-valid search
  passed. This is not browser visual validation.
- Three protected CSV hashes remain unchanged. No migration, production access,
  deploy, push, merge, or commit occurred.
- Production readiness remains blocked by the known active-Lost RLS exposure
  in prepared SQL, lack of isolated database execution, and unverified live
  Auth/Supabase behavior. Historical suggestions to apply SQL are not current
  authorization; follow the explicit no-production-change scope.

## Deployment publication pass — 2026-10-25

- Added `/healthz` for a generic liveness check; the regression test passed.
- Full suite after this addition: **160 passed in 7.60s**. `pip check` found no
  broken requirements. WSGI import passed with debug off and a temporary local
  secret. No vulnerability scanner was available.
- The only connected Render workspace lists no FindBack service and its
  services reference different repositories. No Render service was created,
  configured, or deployed.
- CSV mode is ephemeral on standard service filesystems; Supabase mode has an
  unresolved policy that exposes active Lost reports and an unavailable public
  Auth journey. Public deployment is therefore blocked. The SQL files and
  database guide now include explicit warnings; SQL remains unapplied.
