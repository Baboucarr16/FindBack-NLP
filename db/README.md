# FindBack database (Supabase PostgreSQL)

## Tables (`db/schema.sql`)

| Table | Purpose |
|---|---|
| `profiles` | One row per Supabase Auth user (`id` references `auth.users`). |
| `reports` | Lost/Found reports, user-owned via `owner_id`. `legacy_report_id` preserves CSV IDs (`FB001`…). No contact columns on purpose. |
| `match_results` | Persisted matcher output per lost→found pair (all four component scores + final). Unique per pair so re-runs are idempotent. |
| `claims` | Private ownership claims on a found report (`pending`/`approved`/`rejected`/`withdrawn`, one active claim per user+report). |
| `notifications` | Per-user inbox. Partial unique index on `(user_id, dedupe_key)` for unread rows makes automatic matching duplicate-safe. |

Timestamps on every table; `updated_at` maintained by trigger on `reports`.

## Access control

Row Level Security is enabled on all tables (see policy section in
`schema.sql`): active reports are publicly readable, writes are
owner-scoped, claims are visible only to claimant + report owner,
notifications strictly to their owner. The browser must only ever use
the **anon** key; the **service-role** key stays in the server
environment for the one-off migration and the server-side
notification writer (`src/notify.py`).

## Notification writes (least privilege, by design)

End-user clients can only write their own inbox
(`notifications_insert_own`, see `db/migrations/002_match_notify_writes.sql`),
so cross-user match notices are sent by the server with the
service-role key: the recipient is re-derived from the lost report's
owner, both reports are re-verified, and message text is built
server-side. Without the key, notifying is skipped and counted, never
failed loudly. RLS is never loosened for arbitrary inbox writes.

## Setup (requires a Supabase project)

1. Create a project at https://supabase.com, open the SQL editor, run `db/schema.sql` once.
2. After reviewing, run `db/migrations/002_match_notify_writes.sql` once to let the app persist automatic match pairs and owner-addressed notifications (service-role calls bypass RLS and are unaffected either way).
3. Copy `.env.example` to `.env` and fill in:
   - `SUPABASE_URL`, `SUPABASE_ANON_KEY` (app + browser-safe usage)
   - `SUPABASE_SERVICE_ROLE_KEY` (server-side only: migration + `src/notify.py`; never the browser, never commit)
   - `FLASK_SECRET_KEY` (session signing, generate a random value)
3. `pip install -r requirements.txt` (adds `supabase`, `python-dotenv`).
4. Dry-run the migration (no credentials needed, CSV only read):
   `python db/migrate_csv.py`
5. `python db/migrate_csv.py --execute` (imports rows; skips already-migrated IDs; CSV untouched).

## CSV mode (default, no credentials)

Without `SUPABASE_URL`/`SUPABASE_ANON_KEY` the app runs exactly as
before on `dataset/findback_reports.csv` (anonymous, single-user).
Auth routes render a clear "not configured" message instead of failing.
