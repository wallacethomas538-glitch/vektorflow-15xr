-- VektorFlow Shopify OAuth token persistence
--
-- Run ONCE in the Supabase SQL editor (Dashboard -> SQL Editor -> New query).
-- Creates ONLY public.connected_stores. No existing table is modified.
--
-- After running: complete the Shopify OAuth grant once via
--   GET /api/shopify/oauth/start?shop=<your-shop>.myshopify.com
-- and the access token will persist across Render redeploys.

create table public.connected_stores (
  id           bigint generated always as identity primary key,
  email        text not null,
  platform     text not null,
  store_url    text not null,
  access_token text not null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint connected_stores_unique_store unique (email, platform, store_url)
);

alter table public.connected_stores enable row level security;

create policy "backend_full_access"
  on public.connected_stores
  for all
  to service_role
  using (true)
  with check (true);
