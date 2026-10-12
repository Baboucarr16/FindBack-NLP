-- Migration 003: tighten claim decisions and make writes idempotent.
--
-- Apply only after reviewing and confirming migration 002 is installed.
-- This file is a review draft; it has not been applied to Supabase.

begin;

-- Claimants may file and read their own claims, but only the owner of
-- the found report may decide them. Restrict authenticated updates to
-- status so callers cannot rewrite claim ownership or report linkage.
drop policy if exists claims_update on public.claims;
create policy claims_update on public.claims
    for update using (
        auth.uid() in (
            select owner_id from public.reports where id = report_id
        )
    )
    with check (
        auth.uid() in (
            select owner_id from public.reports where id = report_id
        )
    );

revoke update on public.claims from public, anon, authenticated;
grant update (status) on public.claims to authenticated;

-- Match upserts need UPDATE permission when a pair already exists.
-- Both the existing and replacement pair must involve a report owned
-- by the authenticated writer.
drop policy if exists match_results_update on public.match_results;
create policy match_results_update on public.match_results
    for update using (
        auth.uid() in (
            select owner_id from public.reports
            where id = lost_report_id or id = found_report_id
        )
    )
    with check (
        auth.uid() in (
            select owner_id from public.reports
            where id = lost_report_id or id = found_report_id
        )
    );

grant update on public.match_results to authenticated;

-- Replace unread-only deduplication with a permanent per-user key.
-- Building the new index first makes existing duplicates fail the
-- migration without dropping data or removing the old protection.
create unique index if not exists notifications_dedupe_all_uidx
    on public.notifications (user_id, dedupe_key)
    where dedupe_key is not null;

drop index if exists public.notifications_dedupe_uidx;
alter index public.notifications_dedupe_all_uidx
    rename to notifications_dedupe_uidx;

commit;
