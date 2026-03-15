-- Migration 002: Symbol registry
-- 60 symbols from rabid-raccoon snapshot (34 active, 26 inactive)
-- CRITICAL: Only active DATABENTO symbols may be queried — Kirk got massive bill from inactive ones

create table symbols (
  code         text        primary key,
  display_name text        not null,
  short_name   text        not null,
  description  text,
  tick_size    numeric     not null default 0,
  data_source  data_source not null,
  dataset      text,
  databento_symbol text,
  fred_symbol  text,
  is_active    boolean     not null default false,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create index idx_symbols_active on symbols (is_active) where is_active = true;
create index idx_symbols_data_source on symbols (data_source);

create table symbol_roles (
  id          serial      primary key,
  name        text        not null unique,
  description text
);

create table symbol_role_members (
  role_id     integer     not null references symbol_roles(id) on delete cascade,
  symbol_code text        not null references symbols(code) on delete cascade,
  primary key (role_id, symbol_code)
);

create table symbol_mappings (
  id           serial      primary key,
  from_code    text        not null references symbols(code),
  to_code      text        not null references symbols(code),
  mapping_type text        not null,
  created_at   timestamptz not null default now(),
  unique (from_code, to_code, mapping_type)
);

-- Auto-update updated_at on symbols
create or replace function update_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger trg_symbols_updated_at
  before update on symbols
  for each row execute function update_updated_at();
