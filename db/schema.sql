-- FindBack minimum schema for Supabase (PostgreSQL 15).
--
-- Tables: profiles, reports, match_results, claims, notifications.
-- Public report fields never carry contact details; contact sharing
-- happens only through an approved claim (see claims + RLS below).
-- Run once in the Supabase SQL editor, then create the project
-- .env from .env.example (never commit real keys).
-- SECURITY BLOCKER: the active-report SELECT policy below does not filter
-- report_type, so it exposes active Lost reports to anon/authenticated.
-- This schema is a development draft and is NOT safe for a public service.
-- Redesign report visibility and test the trusted matching path before use.

-- ============================================================
-- PROFILES (one row per authenticated user)
-- ============================================================

create table if not exists public.profiles (
    id uuid primary key references auth.users (id) on delete cascade,
    email text not null,
    display_name text not null default '',
    created_at timestamptz not null default now()
);

-- ============================================================
-- REPORTS (lost and found reports, user-owned)
-- ============================================================

create table if not exists public.reports (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid references public.profiles (id) on delete set null,
    report_type text not null check (report_type in ('Lost', 'Found')),
    item_category text not null default '',
    description text not null default '',
    organization_type text not null default '',
    organization_name text not null default '',
    campus_or_branch text not null default '',
    building_or_terminal text not null default '',
    floor_or_level text not null default '',
    specific_area text not null default '',
    event_date date,
    approx_time time,
    status text not null default 'active'
        check (status in ('active', 'resolved', 'withdrawn')),
    legacy_report_id text unique,
    submission_key uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists reports_owner_idx on public.reports (owner_id);
create index if not exists reports_type_status_idx
    on public.reports (report_type, status);
create unique index if not exists reports_submission_key_uidx
    on public.reports (submission_key)
    where submission_key is not null;

-- ============================================================
-- MATCH RESULTS (persisted matcher output, auditable)
-- ============================================================

create table if not exists public.match_results (
    id uuid primary key default gen_random_uuid(),
    lost_report_id uuid not null
        references public.reports (id) on delete cascade,
    found_report_id uuid not null
        references public.reports (id) on delete cascade,
    semantic_score double precision not null default 0,
    location_score double precision not null default 0,
    time_score double precision not null default 0,
    category_score double precision not null default 0,
    final_score double precision not null default 0,
    created_at timestamptz not null default now(),
    unique (lost_report_id, found_report_id),
    check (lost_report_id <> found_report_id)
);

create index if not exists match_results_lost_idx
    on public.match_results (lost_report_id, final_score desc);

-- ============================================================
-- CLAIMS (private ownership claims on found reports)
-- ============================================================

create table if not exists public.claims (
    id uuid primary key default gen_random_uuid(),
    report_id uuid not null
        references public.reports (id) on delete cascade,
    claimant_id uuid not null
        references public.profiles (id) on delete cascade,
    status text not null default 'pending'
        check (status in ('pending', 'approved', 'rejected', 'withdrawn')),
    claim_note text not null default '',
    created_at timestamptz not null default now(),
    decided_at timestamptz
    -- One open/approved claim at a time; rejected/withdrawn claims may
    -- be filed again later.
);

create unique index if not exists claims_one_open_per_claimant_uidx
    on public.claims (report_id, claimant_id)
    where status in ('pending', 'approved');

create index if not exists claims_report_idx on public.claims (report_id);
create index if not exists claims_claimant_idx on public.claims (claimant_id);

-- ============================================================
-- NOTIFICATIONS (duplicate-safe inbox per user)
-- A permanent partial unique index makes retries idempotent even after
-- the original notification has been read.
-- ============================================================

create table if not exists public.notifications (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null
        references public.profiles (id) on delete cascade,
    kind text not null default 'match'
        check (kind in ('match', 'claim', 'system')),
    title text not null default '',
    body text not null default '',
    related_report_id uuid references public.reports (id) on delete set null,
    dedupe_key text,
    is_read boolean not null default false,
    created_at timestamptz not null default now()
);

create index if not exists notifications_user_idx
    on public.notifications (user_id, is_read, created_at desc);

create unique index if not exists notifications_dedupe_uidx
    on public.notifications (user_id, dedupe_key)
    where dedupe_key is not null;

-- ============================================================
-- UPDATED_AT MAINTENANCE
-- ============================================================

create or replace function public.touch_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists reports_touch on public.reports;
create trigger reports_touch
    before update on public.reports
    for each row execute function public.touch_updated_at();

-- ============================================================
-- ROW LEVEL SECURITY
-- Active reports are public for search. Profiles, claims, matches,
-- and notifications are restricted to their owners/participants.
-- ============================================================

alter table public.profiles enable row level security;
alter table public.reports enable row level security;
alter table public.match_results enable row level security;
alter table public.claims enable row level security;
alter table public.notifications enable row level security;

-- Profiles are private. The Auth provider remains the source of truth.
drop policy if exists profiles_read on public.profiles;
drop policy if exists profiles_write on public.profiles;
drop policy if exists profiles_read_self on public.profiles;
drop policy if exists profiles_insert_self on public.profiles;
create policy profiles_read_self on public.profiles
    for select to authenticated
    using ((select auth.uid()) = id);
create policy profiles_insert_self on public.profiles
    for insert to authenticated
    with check ((select auth.uid()) = id);

-- Active reports remain public; owners can see their own inactive rows.
drop policy if exists reports_read on public.reports;
drop policy if exists reports_insert on public.reports;
drop policy if exists reports_owner_write on public.reports;
drop policy if exists reports_owner_delete on public.reports;
drop policy if exists reports_read_active_or_owner on public.reports;
drop policy if exists reports_insert_owner on public.reports;
create policy reports_read_active_or_owner on public.reports
    for select to anon, authenticated
    using (status = 'active' or (select auth.uid()) = owner_id);
create policy reports_insert_owner on public.reports
    for insert to authenticated
    with check ((select auth.uid()) = owner_id and status = 'active');

-- Match results are visible only to owners of one side. Pairs must be
-- active Lost -> Found reports and inserts require ownership of a side.
drop policy if exists match_results_read on public.match_results;
drop policy if exists match_results_read_participants on public.match_results;
drop policy if exists match_results_insert_owned_pair on public.match_results;
drop policy if exists match_results_update_owned_pair on public.match_results;
drop policy if exists match_results_insert on public.match_results;
drop policy if exists match_results_update on public.match_results;
create policy match_results_read_participants on public.match_results
    for select to authenticated using (
        exists (select 1 from public.reports r where r.id = lost_report_id
                and r.owner_id = (select auth.uid()))
        or exists (select 1 from public.reports r where r.id = found_report_id
                   and r.owner_id = (select auth.uid()))
    );
create policy match_results_insert_owned_pair on public.match_results
    for insert to authenticated with check (
        exists (select 1 from public.reports l where l.id = lost_report_id
                and l.report_type = 'Lost' and l.status = 'active')
        and exists (select 1 from public.reports f where f.id = found_report_id
                    and f.report_type = 'Found' and f.status = 'active')
        and (exists (select 1 from public.reports r where r.id = lost_report_id
                     and r.owner_id = (select auth.uid()))
             or exists (select 1 from public.reports r
                        where r.id = found_report_id
                          and r.owner_id = (select auth.uid())))
    );
create policy match_results_update_owned_pair on public.match_results
    for update to authenticated
    using (
        exists (select 1 from public.reports r where r.id = lost_report_id
                and r.owner_id = (select auth.uid()))
        or exists (select 1 from public.reports r where r.id = found_report_id
                   and r.owner_id = (select auth.uid()))
    )
    with check (
        exists (select 1 from public.reports l where l.id = lost_report_id
                and l.report_type = 'Lost' and l.status = 'active')
        and exists (select 1 from public.reports f where f.id = found_report_id
                    and f.report_type = 'Found' and f.status = 'active')
        and (exists (select 1 from public.reports r where r.id = lost_report_id
                     and r.owner_id = (select auth.uid()))
             or exists (select 1 from public.reports r
                        where r.id = found_report_id
                          and r.owner_id = (select auth.uid())))
    );

-- Claims can only target another user's active Found report. Owners
-- decide pending claims; claimants may only move their claim to withdrawn.
drop policy if exists claims_select on public.claims;
drop policy if exists claims_insert on public.claims;
drop policy if exists claims_update on public.claims;
drop policy if exists claims_select_participants on public.claims;
drop policy if exists claims_insert_self_on_found on public.claims;
drop policy if exists claims_update_participant_status on public.claims;
create policy claims_select_participants on public.claims
    for select to authenticated using (
        claimant_id = (select auth.uid())
        or exists (select 1 from public.reports r where r.id = report_id
                   and r.owner_id = (select auth.uid()))
    );
create policy claims_insert_self_on_found on public.claims
    for insert to authenticated with check (
        claimant_id = (select auth.uid())
        and status = 'pending'
        and exists (select 1 from public.reports r where r.id = report_id
                    and r.report_type = 'Found' and r.status = 'active'
                    and r.owner_id <> (select auth.uid()))
    );
create policy claims_update_participant_status on public.claims
    for update to authenticated
    using (
        claimant_id = (select auth.uid())
        or exists (select 1 from public.reports r where r.id = report_id
                   and r.owner_id = (select auth.uid()))
    )
    with check (
        (claimant_id = (select auth.uid()) and status = 'withdrawn')
        or (status in ('approved', 'rejected')
            and exists (select 1 from public.reports r where r.id = report_id
                        and r.owner_id = (select auth.uid())))
    );

-- Notifications have no authenticated insert policy; the trusted server
-- writer uses service_role. Recipients can only read/update their rows.
drop policy if exists notifications_select on public.notifications;
drop policy if exists notifications_update on public.notifications;
drop policy if exists notifications_select_owner on public.notifications;
drop policy if exists notifications_update_owner on public.notifications;
drop policy if exists notifications_insert_own on public.notifications;
create policy notifications_select_owner on public.notifications
    for select to authenticated using ((select auth.uid()) = user_id);
create policy notifications_update_owner on public.notifications
    for update to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

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
