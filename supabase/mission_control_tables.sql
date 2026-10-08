-- VektorFlow Mission & Control tables
-- Run ONCE in the Supabase SQL editor (project connected via DATABASE_URL).
-- The backend writes here when DATABASE_URL is configured; otherwise it
-- falls back to the ephemeral SQLite file (rows lost on redeploy).
--
-- Safe to re-run: all statements are IF NOT EXISTS.

create table if not exists public.missions (
    id text primary key,
    email text not null,
    objective text not null,
    constraints text not null default '{}',
    priority text not null default 'normal',
    success_criteria text not null default '{}',
    state text not null default 'draft',
    workflow text not null default '{}',
    metadata text not null default '{}',
    created_at text not null,
    updated_at text not null,
    completed_at text
);

create table if not exists public.mission_tasks (
    id text primary key,
    mission_id text not null,
    agent text not null,
    instruction text not null,
    dependencies text not null default '[]',
    risk text not null default 'medium',
    status text not null default 'pending',
    result text not null default '{}',
    created_at text not null,
    updated_at text not null
);

create table if not exists public.action_proposals (
    id text primary key,
    mission_id text,
    task_id text,
    email text not null,
    agent text not null,
    action text not null,
    risk text not null default 'medium',
    decision text not null default 'pending',
    policy text not null default 'ask',
    reason text not null default '',
    payload text not null default '{}',
    created_at text not null,
    resolved_at text
);

create table if not exists public.mission_audit (
    id text primary key,
    mission_id text not null,
    actor text not null,
    event_type text not null,
    from_state text,
    to_state text,
    details text not null default '{}',
    created_at text not null
);

create index if not exists idx_missions_email_state on public.missions(email, state);
create index if not exists idx_tasks_mission on public.mission_tasks(mission_id);
create index if not exists idx_proposals_mission on public.action_proposals(mission_id);
create index if not exists idx_audit_mission on public.mission_audit(mission_id, created_at);
