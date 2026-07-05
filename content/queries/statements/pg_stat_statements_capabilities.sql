with settings as (
  select name, setting
  from pg_settings
  where name in (
    'shared_preload_libraries',
    'compute_query_id',
    'track_io_timing',
    'track_wal_io_timing',
    'track_functions',
    'pg_stat_statements.max',
    'pg_stat_statements.track',
    'pg_stat_statements.track_planning',
    'pg_stat_statements.track_utility'
  )
),
capabilities as (
  select 'extension_available' as capability,
         exists (select 1 from pg_available_extensions where name = 'pg_stat_statements')::text as value,
         'pg_available_extensions' as source
  union all
  select 'extension_installed',
         exists (select 1 from pg_extension where extname = 'pg_stat_statements')::text,
         'pg_extension'
  union all
  select 'view_available',
         (to_regclass('pg_stat_statements') is not null)::text,
         'to_regclass'
  union all
  select 'preloaded',
         exists (
           select 1
           from regexp_split_to_table(coalesce((select setting from settings where name = 'shared_preload_libraries'), ''), ',') as lib(name)
           where btrim(lib.name) = 'pg_stat_statements'
         )::text,
         'shared_preload_libraries'
  union all
  select 'compute_query_id',
         coalesce((select setting from settings where name = 'compute_query_id'), '<missing>'),
         'pg_settings'
  union all
  select 'track_io_timing',
         coalesce((select setting from settings where name = 'track_io_timing'), '<missing>'),
         'pg_settings'
  union all
  select 'track_wal_io_timing',
         coalesce((select setting from settings where name = 'track_wal_io_timing'), '<missing>'),
         'pg_settings'
  union all
  select 'track_functions',
         coalesce((select setting from settings where name = 'track_functions'), '<missing>'),
         'pg_settings'
  union all
  select 'pg_stat_statements.max',
         coalesce((select setting from settings where name = 'pg_stat_statements.max'), '<missing>'),
         'pg_settings'
  union all
  select 'pg_stat_statements.track',
         coalesce((select setting from settings where name = 'pg_stat_statements.track'), '<missing>'),
         'pg_settings'
  union all
  select 'pg_stat_statements.track_planning',
         coalesce((select setting from settings where name = 'pg_stat_statements.track_planning'), '<missing>'),
         'pg_settings'
  union all
  select 'pg_stat_statements.track_utility',
         coalesce((select setting from settings where name = 'pg_stat_statements.track_utility'), '<missing>'),
         'pg_settings'
)
select
  capability,
  value,
  source,
  case
    when capability = 'extension_available' and value <> 'true' then 'extension package is not available'
    when capability = 'extension_installed' and value <> 'true' then 'run CREATE EXTENSION pg_stat_statements in this database'
    when capability = 'view_available' and value <> 'true' then 'view is unavailable in current search_path/database'
    when capability = 'preloaded' and value <> 'true' then 'add pg_stat_statements to shared_preload_libraries and restart PostgreSQL'
    when capability = 'compute_query_id' and value not in ('on', 'auto') then 'set compute_query_id=on or auto for stable query_id tracking'
    when capability = 'track_io_timing' and value <> 'on' then 'enable track_io_timing for read/write timing columns'
    when capability = 'track_functions' and value = 'none' then 'set track_functions to pl or all for function workload stats'
    else 'ok'
  end as recommendation
from capabilities
order by capability
