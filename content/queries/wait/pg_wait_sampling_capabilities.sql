select
  'extension_available' as capability,
  exists (select 1 from pg_available_extensions where name = 'pg_wait_sampling')::text as value,
  'pg_available_extensions' as source,
  case
    when exists (select 1 from pg_available_extensions where name = 'pg_wait_sampling') then 'ok'
    else 'extension package is not available'
  end as recommendation
union all
select
  'extension_installed',
  exists (select 1 from pg_extension where extname = 'pg_wait_sampling')::text,
  'pg_extension',
  case
    when exists (select 1 from pg_extension where extname = 'pg_wait_sampling') then 'ok'
    else 'optional: install pg_wait_sampling for historical wait samples'
  end
union all
select
  'profile_view_available',
  (to_regclass('pg_wait_sampling_profile') is not null)::text,
  'to_regclass on pg_diag search_path',
  case
    when to_regclass('pg_wait_sampling_profile') is not null then 'ok'
    else 'profile view is not available on pg_catalog, public search_path'
  end
union all
select
  'extension_schema',
  coalesce(
    (select namespace.nspname from pg_extension extension
     join pg_namespace namespace on namespace.oid = extension.extnamespace
     where extension.extname = 'pg_wait_sampling'),
    '<not installed>'
  ),
  'pg_extension',
  'informational: pg_diag can query the profile when its view is on the configured search path'
order by capability
