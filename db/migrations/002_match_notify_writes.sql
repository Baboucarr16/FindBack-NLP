-- Migration 002: allow the app to persist automatic matching output.
--
-- Context: schema.sql ships only SELECT policies on match_results and
-- notifications, so authenticated inserts are currently denied. The
-- auto_match engine (src/auto_match.py) runs with the finder's user
-- client, so policies below permit exactly that flow and nothing more.
-- Service-role calls bypass RLS and are unaffected either way.
--
-- Known limit (by design): notifications addressed to OTHER users
-- (the lost report's owner) cannot be inserted by an end-user client
-- under least privilege; those inserts need service-role execution,
-- which is not configured. The engine records such denials in its
-- error count instead of failing. Do NOT loosen
-- notifications_insert_own to allow cross-user inserts: any signed-in
-- user could then spam any inbox.
--
-- Apply once in the Supabase SQL editor AFTER reviewing.

-- Match pairs: the inserting user must own at least one side of the
-- pair. This permits the real engine flow (the finder owns the found
-- side) while denying forged pairs between strangers' reports.
-- Fail-closed: rows with NULL owner_id never satisfy the check.
drop policy if exists match_results_insert on public.match_results;
create policy match_results_insert on public.match_results
    for insert with check (
        auth.uid() in (
            select owner_id from public.reports
            where id = lost_report_id or id = found_report_id
        )
    );

-- Notifications: users may only create their OWN notifications.
drop policy if exists notifications_insert_own on public.notifications;
create policy notifications_insert_own on public.notifications
    for insert with check (auth.uid() = user_id);
