-- VektorFlow Second Brain <-> Termux relay

CREATE TABLE IF NOT EXISTS public.termux_relays (
  relay_id text PRIMARY KEY,
  hostname text NOT NULL DEFAULT '',
  status text NOT NULL DEFAULT 'offline',
  executors text[] NOT NULL DEFAULT '{}',
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  version text NOT NULL DEFAULT '1'
);

CREATE TABLE IF NOT EXISTS public.termux_jobs (
  id text PRIMARY KEY,
  target text NOT NULL CHECK (target IN ('hermes','codex','opencode','shell')),
  action text NOT NULL,
  instruction text NOT NULL,
  working_dir text NOT NULL DEFAULT '~/vektorflow-15xr',
  timeout_seconds integer NOT NULL DEFAULT 300 CHECK (timeout_seconds BETWEEN 10 AND 900),
  approval_required boolean NOT NULL DEFAULT true,
  approved_at timestamptz,
  status text NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued','running','completed','failed','cancelled')),
  requested_by text NOT NULL DEFAULT 'commander@vektorflow.com',
  stdout text NOT NULL DEFAULT '',
  stderr text NOT NULL DEFAULT '',
  exit_code integer,
  result jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  completed_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_termux_jobs_queue ON public.termux_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_termux_jobs_requested_by ON public.termux_jobs(requested_by, created_at DESC);
