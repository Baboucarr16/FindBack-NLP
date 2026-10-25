# FindBack database (Supabase PostgreSQL)

## Tables

`db/schema.sql` defines `profiles`, `reports`, `match_results`, `claims`,
and `notifications`. **Security blocker:** the current report SELECT policy
allows public reads of every active report, including Lost reports. It does
not yet implement the intended Found-public/Lost-private boundary. Do not use
this SQL for a public/shared deployment. Profiles are self-readable; match
results are visible only to owners of either report; claims are visible to
their claimant and the found-report owner; notifications are private to their
recipient. No report contact fields are stored.

The browser uses no Supabase client or service-role credential. Flask
uses the anon key with the signed-in user's session for ordinary reads
and writes. The service-role key is server-side only and is used by the
CSV importer and `src/notify.py` for cross-user notifications. The
notification writer rechecks report ownership and active state before
writing.

## Ordered schema setup

1. Use only a disposable/test Supabase project; never run the current draft
   SQL against production or a shared project.
2. `db/schema.sql` and `db/migrations/004_core_dataflow_security.sql` are
   drafts. Their active-report policy exposes active Lost reports. They may
   only be used for isolated policy review with synthetic data until a
   trusted matching design and private Lost-report policy are implemented.
   Migration 004 assumes the five tables from `schema.sql`
   exist, but does not depend on drafts 002 or 003. It reconciles the
   policy and privilege set, adds report-submission idempotency, permits
   closed claims to be re-filed, and makes notification dedupe permanent.
3. Do not apply migrations 002 or 003 separately for the current app;
   004 replaces their policy behavior. Their presence in the repository
   is not evidence they were applied to a project.
4. Copy `.env.example` to `.env` and fill in `SUPABASE_URL`,
   `SUPABASE_ANON_KEY`, server-only `SUPABASE_SERVICE_ROLE_KEY`, and a
   random `FLASK_SECRET_KEY`. Use `FLASK_DEBUG=0` and HTTPS in
   production. Configure Supabase Auth Site URL and allowed redirect
   URLs for the app origin when email confirmation is enabled.
5. Install dependencies with `pip install -r requirements.txt`.
6. Validate the CSV import without writing: `python db/migrate_csv.py`.
   `python db/migrate_csv.py --execute` inserts rows and leaves the CSV
   untouched. It writes to the project named by `SUPABASE_URL`; do not
   point it at production during testing.

Migration 004 includes rollback notes. Its policy rollback requires a
reviewed policy snapshot; blindly restoring the old policies would
reopen profile, match, and claim access. Index creation intentionally
fails if existing data contains duplicate dedupe keys or multiple open
claims for the same user/report pair.

## Storage modes

With `FINDBACK_STORE=csv` (the default), the app uses
`dataset/findback_reports.csv` anonymously. With
`FINDBACK_STORE=supabase`, users must sign in to persist either Lost or
Found reports. Search reads active Found reports from Supabase and uses
the existing Sentence-BERT matching algorithm and weights. If Supabase
is selected without credentials, report routes show a configuration
error rather than silently switching to CSV.

Google OAuth is not implemented. If needed later, separately enable the
provider in Supabase Auth, configure its provider credentials and
redirect allowlist, and add an application callback/return route.

## Phase 2 SQL status

Migration 004 is prepared but has not been applied. Its RLS behavior has
only been reviewed in code and checked by static regression tests. No
local Supabase/Postgres test database was available, and no production
connection was made. Policy execution, grants, migration rerun behavior,
and index creation against existing data remain unverified until tested
on an isolated Supabase project.
