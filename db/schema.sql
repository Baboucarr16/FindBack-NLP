-- FindBack minimum schema for Supabase (PostgreSQL 15).
--
-- Tables: profiles, reports, match_results, claims, notifications.
-- Public report fields never carry contact details; contact sharing
-- happens only through an approved claim (see claims + RLS below).
-- Run once in the Supabase SQL editor, then create the project
-- .env from .env.example (never commit real keys).

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
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists reports_owner_idx on public.reports (owner_id);
create index if not exists reports_type_status_idx
    on public.reports (report_type, status);

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
    decided_at timestamptz,
    unique (report_id, claimant_id)
);

create index if not exists claims_report_idx on public.claims (report_id);
create index if not exists claims_claimant_idx on public.claims (claimant_id);

-- ============================================================
-- NOTIFICATIONS (duplicate-safe inbox per user)
-- A partial unique index lets the app re-run automatic matching
-- without creating a second identical unread notification.
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
    where dedupe_key is not null and is_read = false;

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
-- Active reports are publicly readable (no contact fields exist
-- on reports). Everything else is owner-scoped.
-- ============================================================

alter table public.profiles enable row level security;
alter table public.reports enable row level security;
alter table public.match_results enable row level security;
alter table public.claims enable row level security;
alter table public.notifications enable row level security;

-- Profiles: readable by anyone, writable by owner.
drop policy if exists profiles_read on public.profiles;
create policy profiles_read on public.profiles
    for select using (true);

drop policy if exists profiles_write on public.profiles;
create policy profiles_write on public.profiles
    for all using (auth.uid() = id) with check (auth.uid() = id);

-- Reports: active reports readable by anyone (anon + authenticated);
-- inserts by authenticated users; updates/deletes by owner only.
drop policy if exists reports_read on public.reports;
create policy reports_read on public.reports
    for select using (status = 'active');

drop policy if exists reports_insert on public.reports;
create policy reports_insert on public.reports
    for insert with check (auth.uid() = owner_id);

drop policy if exists reports_owner_write on public.reports;
create policy reports_owner_write on public.reports
    for update using (auth.uid() = owner_id)
    with check (auth.uid() = owner_id);

drop policy if exists reports_owner_delete on public.reports;
create policy reports_owner_delete on public.reports
    for delete using (auth.uid() = owner_id);

-- Match results: readable with the underlying active reports.
drop policy if exists match_results_read on public.match_results;
create policy match_results_read on public.match_results
    for select using (true);

-- Claims: visible to the claimant and to the report owner.
drop policy if exists claims_select on public.claims;
create policy claims_select on public.claims
    for select using (
        auth.uid() = claimant_id
        or auth.uid() in (
            select owner_id from public.reports where id = report_id
        )
    );

drop policy if exists claims_insert on public.claims;
create policy claims_insert on public.claims
    for insert with check (auth.uid() = claimant_id);

drop policy if exists claims_update on public.claims;
create policy claims_update on public.claims
    for update using (
        auth.uid() = claimant_id
        or auth.uid() in (
            select owner_id from public.reports where id = report_id
        )
    );

-- Notifications: strictly owner-visible.
drop policy if exists notifications_select on public.notifications;
create policy notifications_select on public.notifications
    for select using (auth.uid() = user_id);

drop policy if exists notifications_update on public.notifications;
create policy notifications_update on public.notifications
    for update using (auth.uid() = user_id)
    with check (auth.uid() = user_id);
