-- Migration 004: reconcile existing core tables with the Flask data flow.
--
-- Prerequisite: db/schema.sql has created profiles, reports,
-- match_results, claims, and notifications. This migration does not
-- depend on migrations 002 or 003; it drops/replaces their named
-- policies and establishes the complete policy set below.
--
-- Apply to a disposable/test project first. It is intentionally not
-- applied by this repository change. The index creation fails closed
-- if existing data contains duplicate permanent notification keys.
-- SECURITY BLOCKER: reports_read_active_or_owner below exposes every
-- active report, including Lost reports, to anon/authenticated. Do NOT
-- apply to a public/shared project until report visibility is redesigned
-- and the cross-owner matcher is moved behind a trusted server boundary.
--
-- Rollback notes: policy rollback requires restoring a reviewed policy
-- snapshot; blindly restoring the old policies would reopen profile,
-- match, and claim access. The submission_key column/index and partial
-- claim index can be removed after deployments stop using them, but
-- doing so removes report retry idempotency and permits closed claims
-- to be re-filed only according to the restored constraint. To restore
-- the former all-time claim uniqueness, first verify there are no repeat
-- report/claimant pairs, then drop claims_one_open_per_claimant_uidx and
-- add UNIQUE (report_id, claimant_id). To restore unread-only notification
-- dedupe, verify duplicates then replace notifications_dedupe_uidx with
-- the prior predicate `WHERE dedupe_key IS NOT NULL AND is_read = false`.

begin;

alter table public.reports
    add column if not exists submission_key uuid;

create unique index if not exists reports_submission_key_uidx
    on public.reports (submission_key)
    where submission_key is not null;

alter table public.claims
    drop constraint if exists claims_report_id_claimant_id_key;

create unique index if not exists claims_one_open_per_claimant_uidx
    on public.claims (report_id, claimant_id)
    where status in ('pending', 'approved');

drop index if exists public.notifications_dedupe_all_uidx;
drop index if exists public.notifications_dedupe_uidx;
create unique index notifications_dedupe_uidx
    on public.notifications (user_id, dedupe_key)
    where dedupe_key is not null;

alter table public.profiles enable row level security;
alter table public.reports enable row level security;
alter table public.match_results enable row level security;
alter table public.claims enable row level security;
alter table public.notifications enable row level security;

-- Remove policy names used by the base schema and prior review drafts.
drop policy if exists profiles_read on public.profiles;
drop policy if exists profiles_write on public.profiles;
drop policy if exists profiles_read_self on public.profiles;
drop policy if exists profiles_insert_self on public.profiles;

drop policy if exists reports_read on public.reports;
drop policy if exists reports_insert on public.reports;
drop policy if exists reports_owner_write on public.reports;
drop policy if exists reports_owner_delete on public.reports;

drop policy if exists match_results_read on public.match_results;
drop policy if exists match_results_insert on public.match_results;
drop policy if exists match_results_update on public.match_results;

drop policy if exists claims_select on public.claims;
drop policy if exists claims_insert on public.claims;
drop policy if exists claims_update on public.claims;

drop policy if exists notifications_select on public.notifications;
drop policy if exists notifications_update on public.notifications;
drop policy if exists notifications_insert_own on public.notifications;

-- Profiles contain email addresses. A user can only read or create
-- their own profile; the Auth provider remains the source of truth.
create policy profiles_read_self on public.profiles
    for select to authenticated
    using ((select auth.uid()) = id);

create policy profiles_insert_self on public.profiles
    for insert to authenticated
    with check ((select auth.uid()) = id);

-- Active reports remain public for search. Owners may also see their
-- inactive reports. Writes require ownership; the app has no report
-- update/delete flow, so no such grants or policies are provided.
create policy reports_read_active_or_owner on public.reports
    for select to anon, authenticated
    using (status = 'active' or (select auth.uid()) = owner_id);

create policy reports_insert_owner on public.reports
    for insert to authenticated
    with check (
        (select auth.uid()) = owner_id
        and status = 'active'
        and report_type in ('Lost', 'Found')
    );

-- A match is visible only to a user who owns one of its reports.
-- Inserts/updates must link active Lost and Found reports, and the
-- authenticated writer must own at least one side.
create policy match_results_read_participants on public.match_results
    for select to authenticated
    using (
        exists (select 1 from public.reports r
                where r.id = lost_report_id
                  and r.owner_id = (select auth.uid()))
        or exists (select 1 from public.reports r
                   where r.id = found_report_id
                     and r.owner_id = (select auth.uid()))
    );

create policy match_results_insert_owned_pair on public.match_results
    for insert to authenticated
    with check (
        exists (select 1 from public.reports l
                where l.id = lost_report_id
                  and l.report_type = 'Lost' and l.status = 'active')
        and exists (select 1 from public.reports f
                    where f.id = found_report_id
                      and f.report_type = 'Found' and f.status = 'active')
        and (
            exists (select 1 from public.reports r
                    where r.id = lost_report_id
                      and r.owner_id = (select auth.uid()))
            or exists (select 1 from public.reports r
                       where r.id = found_report_id
                         and r.owner_id = (select auth.uid()))
        )
    );

create policy match_results_update_owned_pair on public.match_results
    for update to authenticated
    using (
        exists (select 1 from public.reports r
                where r.id = lost_report_id
                  and r.owner_id = (select auth.uid()))
        or exists (select 1 from public.reports r
                   where r.id = found_report_id
                     and r.owner_id = (select auth.uid()))
    )
    with check (
        exists (select 1 from public.reports l
                where l.id = lost_report_id
                  and l.report_type = 'Lost' and l.status = 'active')
        and exists (select 1 from public.reports f
                    where f.id = found_report_id
                      and f.report_type = 'Found' and f.status = 'active')
        and (
            exists (select 1 from public.reports r
                    where r.id = lost_report_id
                      and r.owner_id = (select auth.uid()))
            or exists (select 1 from public.reports r
                       where r.id = found_report_id
                         and r.owner_id = (select auth.uid()))
        )
    );

-- Claims can only be filed against another user's active Found report.
-- A participant can read a claim. Only the report owner can decide it;
-- a claimant may change status only to withdrawn.
create policy claims_select_participants on public.claims
    for select to authenticated
    using (
        claimant_id = (select auth.uid())
        or exists (select 1 from public.reports r
                   where r.id = report_id
                     and r.owner_id = (select auth.uid()))
    );

create policy claims_insert_self_on_found on public.claims
    for insert to authenticated
    with check (
        claimant_id = (select auth.uid())
        and status = 'pending'
        and exists (select 1 from public.reports r
                    where r.id = report_id
                      and r.report_type = 'Found'
                      and r.status = 'active'
                      and r.owner_id <> (select auth.uid()))
    );

create policy claims_update_participant_status on public.claims
    for update to authenticated
    using (
        claimant_id = (select auth.uid())
        or exists (select 1 from public.reports r
                   where r.id = report_id
                     and r.owner_id = (select auth.uid()))
    )
    with check (
        (claimant_id = (select auth.uid()) and status = 'withdrawn')
        or (
            status in ('approved', 'rejected')
            and exists (select 1 from public.reports r
                        where r.id = report_id
                          and r.owner_id = (select auth.uid()))
        )
    );

-- Notifications are private to their recipient. Inserts are reserved
-- for trusted server-side service-role code, never end-user clients.
create policy notifications_select_owner on public.notifications
    for select to authenticated
    using ((select auth.uid()) = user_id);

create policy notifications_update_owner on public.notifications
    for update to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

-- Remove inherited/default table access, then grant only the operations
-- used by this application. Service-role notification writes bypass RLS.
revoke all on public.profiles, public.reports, public.match_results,
    public.claims, public.notifications from public, anon, authenticated;

grant select, insert on public.profiles to authenticated;
grant select (id, report_type, item_category, description,
              organization_type, organization_name, campus_or_branch,
              building_or_terminal, floor_or_level, specific_area,
              event_date, approx_time, status, legacy_report_id,
              created_at, updated_at)
    on public.reports to anon, authenticated;
grant select (owner_id) on public.reports to authenticated;
grant select (submission_key) on public.reports to authenticated;
grant insert (owner_id, report_type, item_category, description,
              organization_type, organization_name, campus_or_branch,
              building_or_terminal, floor_or_level, specific_area,
              event_date, approx_time, status, submission_key)
    on public.reports to authenticated;
grant select, insert, update on public.match_results to authenticated;
grant select on public.claims to authenticated;
grant insert (report_id, claimant_id, claim_note)
    on public.claims to authenticated;
grant update (status) on public.claims to authenticated;
grant select on public.notifications to authenticated;
grant update (is_read) on public.notifications to authenticated;
grant all on public.notifications to service_role;
grant select on public.reports to service_role;

commit;
