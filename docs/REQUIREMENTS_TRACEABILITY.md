# FindBack requirements traceability audit

**Audit snapshot:** 2026-10-25<br>
**Repository:** integration worktree, branch `integration/production-readiness-ui`<br>
**Evidence limits:** no official course assignment/rubric was present in the repository. This matrix traces the stated project goals and behavior evidenced by code, docs, tests, and the local offline smoke run. No production Supabase project was contacted.

Status meanings: **Verified** means the stated local behavior was observed in a test or isolated local flow; **Implemented but unverified** means code exists but was not exercised against its real dependency; **Partially implemented** means only some modes or paths work; **Missing** means no implementation was found; **Blocked** means evidence could not safely be obtained; **Not applicable** means outside this version's requirements.

| Requirement | Evidence in code or documentation | Verification method | Status | Remaining work |
|---|---|---|---|---|
| Start the Flask application locally | `app.py`, `wsgi.py`, `Procfile`, `README.md` | WSGI import regression test and local Flask test-client smoke; no long-running public server exposed | Verified locally | Repeat on presentation machine and confirm Python/dependencies/model cache. |
| Search a lost-item description against found reports | `/search` in `app.py`; `src/semantic_matcher.py`; `templates/results.html` | Offline local workflow returned HTTP 200 and synthetic candidate FB002 | Verified locally | Browser rendering remains unverified. |
| Preserve existing four-component score | `src/semantic_matcher.py`, `src/matcher.py`, `src/auto_match.py`, `src/explain.py` | Unit tests and source review | Verified in code/tests | The weights and similarity are not empirically calibrated; do not call the score probability. |
| Explain why a candidate appeared | `src/explain.py`; results template | Unit and route tests; offline results page showed disclaimer | Verified locally | Explanations are heuristic field comparisons, not causal model explanations. |
| Search has useful empty/invalid states | `/search` in `app.py`; `tests/test_app.py`, `tests/test_theme.py` | Flask route tests for validation, empty result, and weak-score filter | Verified by tests | Visual states need browser review. |
| Submit a found report in local CSV mode | `found()` and `save_found_report()` in `app.py` | Route tests use temporary files; separate offline smoke created FB027 in a disposable copy and found it in a later query | Verified locally in isolated storage | Do not submit while the app points at the checked-in CSV. CSV append has no cross-process idempotency or file lock. |
| Persist lost searches in CSV mode | `search()` in `app.py` | Code trace: CSV branch constructs a transient Lost dictionary and does not append it | Missing by design | State this limitation; add a local persistent Lost-report product flow only if required. |
| Select actual storage mode from `FINDBACK_STORE` | `using_supabase()`, `supabase_requested()`, `invalid_storage_mode()` in `app.py`; `src/store.py` | Route tests for CSV/Supabase selection, missing configuration, and Supabase fakes | Verified in local code/tests | The `get_store()` factory is not the route abstraction; app branches directly and CSV helper functions remain in `app.py`. |
| Supabase Lost/Found persistence and matching | `/search`, `/found`; `SupabaseStore`; semantic matcher | Mocked client and matcher tests | Implemented but unverified against PostgreSQL/Supabase | No local database available; migration 004 has not been applied; no service was contacted. |
| Supabase authentication end to end | `src/auth.py`; `/login` and `/register` routes | Unit/route tests stub Supabase; public credential forms were deliberately removed from templates | Implemented but unverified; no public browser journey | Do not demonstrate or claim live Auth. Authentication UI must be deliberately restored before a user-facing Supabase workflow is usable. |
| Google OAuth | Repository search and `src/auth.py` | Route/provider search | Missing | Separate provider enablement, credentials, callback, and redirect allowlist work would be needed. |
| Claim filing and owner decisions | `/claims*` routes, `SupabaseStore.create_claim()` / `decide_claim()`, RLS in `db/schema.sql` and migration 004 | Flask tests and static SQL assertions | Implemented but unverified against database | User-facing workflow depends on Supabase Auth, which has no public form currently. SQL/RLS needs isolated execution. |
| Match notifications | `/search`, `/found`, `src/auto_match.py`, `src/notify.py` | Fake-store/service-client tests | Implemented but unverified against Supabase | Server-only service-role path and RLS must be tested in an isolated project. A missing key intentionally skips notification creation. |
| Restrict profiles, match results, claims, and inbox records | `db/schema.sql`, `db/migrations/004_core_dataflow_security.sql` | Static SQL contract tests | Implemented but unverified against PostgreSQL | Static string assertions do not prove role/grant behavior. Migration remains unexecuted. |
| Keep active lost-report data private to its owner | Current report SELECT policy permits every active report to `anon` and `authenticated` | Policy review at `db/schema.sql:177-179` and migration 004:88-90 | Partially implemented / security gap | Separate Found-public and Lost-private access. Rework the global auto-matcher to use an explicitly trusted server-side path before tightening RLS. Review the live policy snapshot only with separate authorization. |
| Remove public authentication UI | Shared shell and account templates; `tests/test_ui_templates.py` | Anonymous and authenticated rendered-home tests; direct account-route tests; template search | Verified in rendered templates | Direct POST handlers still exist for internal use; pages/routes remain reachable by URL but no credential form is provided. |
| Theme follows system and persists a choice | `static/theme.js`, shared base, CSS tokens | Static asset/markup regression tests | Implemented but browser-unverified | Check actual toggle interaction and contrast in a browser on desktop/mobile. |
| Identify dataset provenance | `README.md`, `benchmark/README.md`, dataset contents/IDs | Docs and local data inspection | Verified: checked-in report/evaluation rows are synthetic examples | Never describe them as real community reports. |
| Evidence-based model quality | `benchmark/dev`, `benchmark/heldout_test`, `src/benchmark_evaluate.py` | Ran the benchmark evaluator and leakage checker | Blocked by absent real labels | Current benchmark contains only EXAMPLE placeholders; no valid accuracy/Top-k/MRR claim is available. |
| Gemini comparison | No integration; no verified real labeled benchmark | Repository inspection; no API calls | Blocked | Collect consented, anonymized dev labels; hold out independent test cases; separately authorize any paid API call. |
| Safe evaluation scripts preserve the checked-in CSVs | `src/artifact_paths.py`; three legacy writer scripts; `.gitignore`; `tests/test_data_artifact_safety.py` | Seven focused regression tests; protected hashes after tests | Verified in code/tests | Legacy evaluations are still based on hard-coded synthetic pair IDs and are not performance evidence. |
| Production deployment readiness | WSGI/Procfile, session store, CSV behavior, SQL docs | Code review only | Partially implemented | Need isolated database/RLS tests, public auth flow decision, Lost report privacy design, production configuration review, and browser QA. No deployment performed. |

## Current demo scope

The verified demo is the local anonymous CSV search, its candidate/evidence
rendering, and a walk-through of the found form. Found submission was verified
only against a temporary copy. The synthetic benchmark cannot support accuracy
claims. Supabase, Auth, claims, and notifications are code-reviewed/mock-tested
only, not an end-to-end demo path.

## Final master-pass update — 2026-10-25

- The homepage and results page now explicitly label the default local CSV
  examples as synthetic when CSV mode is selected. This does not label results
  in Supabase mode.
- The two homepage decorative pseudo-elements no longer use `100vw`; their
  widths are constrained to their sections to avoid classic-scrollbar overflow.
  A CSS contract regression test covers this source-level condition. Browser
  layout verification is still unavailable.
- Baseline before this pass: **156 passed**. Final complete suite after this
  pass: **159 passed** (`python -m pytest tests/ -q
  --basetemp=.pytest-master-final3`). UI/theme subset: **19 passed**.
- Local HTTP verification on port 5187 returned 200 for `/`, `/found`,
  `/login`, `/register`, `/static/style.css`, and `/static/theme.js`. A
  CSRF-valid sample search returned 200, included synthetic candidate FB002,
  and retained the ownership disclaimer.
- Dataset hashes remained unchanged. No browser screenshot, responsive
  rendering, console, or keyboard inspection was available.

## Deployment audit addendum — 2026-10-25

- Added and tested `GET /healthz`; it returns a generic liveness status without
  querying the database or loading the matching model.
- Final full suite: **160 passed in 7.60s**. `pip check` reported no broken
  requirements and the production WSGI import succeeded under safe local
  settings. No dependency vulnerability scanner is installed.
- Render discovery found no FindBack service in the only connected workspace.
  Deployment is blocked by the public Lost-report policy, lack of a verified
  Auth journey, and ephemeral CSV writes. No service or production setting was
  changed.
