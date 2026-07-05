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
  'to_regclass',
  case
    when to_regclass('pg_wait_sampling_profile') is not null then 'ok'
    else 'profile view is not available'
  end
order by capability
