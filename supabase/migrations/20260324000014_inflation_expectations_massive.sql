-- Move inflation expectations ownership from FRED to Massive.
-- Keep realized inflation (e.g., CPI/core) on FRED.

insert into sources (name, description, base_url, api_key_env, is_active)
values (
  'massive',
  'Massive economy endpoints (inflation expectations)',
  'https://api.massive.com/fed/v1',
  'MASSIVE_API_KEY',
  true
)
on conflict (name) do update
set
  description = excluded.description,
  base_url = excluded.base_url,
  api_key_env = excluded.api_key_env,
  is_active = excluded.is_active;

update series_catalog
set is_active = false
where series_id in ('T5YIE', 'T10YIE');
