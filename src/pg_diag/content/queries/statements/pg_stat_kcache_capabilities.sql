with extension_info as (
  select extension.oid, extension.extversion, namespace.nspname as extension_schema
  from pg_extension extension
  join pg_namespace namespace on namespace.oid = extension.extnamespace
  where extension.extname = 'pg_stat_kcache'
),
api_info as (
  select
    exists (
      select 1
      from pg_proc proc
      join pg_depend dependency
        on dependency.classid = 'pg_proc'::regclass
       and dependency.objid = proc.oid
       and dependency.deptype = 'e'
      join extension_info extension on extension.oid = dependency.refobjid
      where proc.proname = 'pg_stat_kcache' and proc.pronargs = 0
    ) as function_available,
    exists (
      select 1
      from pg_proc proc
      join pg_depend dependency
        on dependency.classid = 'pg_proc'::regclass
       and dependency.objid = proc.oid
       and dependency.deptype = 'e'
      join extension_info extension on extension.oid = dependency.refobjid
      where
        proc.proname = 'pg_stat_kcache'
        and proc.pronargs = 0
        and 'stats_since' = any(coalesce(proc.proargnames, array[]::text[]))
    ) as delta_api_available
),
settings as (
  select name, setting
  from pg_settings
  where name in (
    'shared_preload_libraries',
    'pg_stat_kcache.track',
    'pg_stat_kcache.track_planning',
    'pg_stat_kcache.linux_hz'
  )
),
preload as (
  select
    (select setting from settings where name = 'shared_preload_libraries') as libraries,
    coalesce(
      array_position(
        array(
          select btrim(library.name)
          from regexp_split_to_table(
            coalesce((select setting from settings where name = 'shared_preload_libraries'), ''),
            ','
          ) as library(name)
        ),
        'pg_stat_statements'
      ),
      0
    ) as pgss_position,
    coalesce(
      array_position(
        array(
          select btrim(library.name)
          from regexp_split_to_table(
            coalesce((select setting from settings where name = 'shared_preload_libraries'), ''),
            ','
          ) as library(name)
        ),
        'pg_stat_kcache'
      ),
      0
    ) as kcache_position
),
capabilities as (
  select 'extension_available'::text as capability,
         exists (select 1 from pg_available_extensions where name = 'pg_stat_kcache')::text as value,
         'pg_available_extensions'::text as source
  union all
  select 'extension_installed', exists (select 1 from extension_info)::text, 'pg_extension'
  union all
  select 'extension_version', coalesce((select extversion from extension_info), '<not installed>'), 'pg_extension'
  union all
  select 'extension_schema', coalesce((select extension_schema from extension_info), '<not installed>'), 'pg_extension'
  union all
  select 'function_available', function_available::text, 'pg_proc extension membership' from api_info
  union all
  select 'delta_api_2_3', delta_api_available::text, 'pg_proc output arguments' from api_info
  union all
  select 'pg_stat_statements_installed',
         exists (select 1 from pg_extension where extname = 'pg_stat_statements')::text,
         'pg_extension'
  union all
  select 'preloaded',
         case when libraries is null then '<hidden>' else (kcache_position > 0)::text end,
         'shared_preload_libraries'
  from preload
  union all
  select 'preload_order',
         case
           when libraries is null then '<hidden>'
           when pgss_position = 0 or kcache_position = 0 then 'incomplete'
           when pgss_position < kcache_position then 'pg_stat_statements_before_pg_stat_kcache'
           else 'incorrect'
         end,
         'shared_preload_libraries'
  from preload
  union all
  select 'pg_stat_kcache.track',
         coalesce((select setting from settings where name = 'pg_stat_kcache.track'), '<missing>'),
         'pg_settings'
  union all
  select 'pg_stat_kcache.track_planning',
         coalesce((select setting from settings where name = 'pg_stat_kcache.track_planning'), '<missing>'),
         'pg_settings'
  union all
  select 'pg_stat_kcache.linux_hz',
         coalesce((select setting from settings where name = 'pg_stat_kcache.linux_hz'), '<missing>'),
         'pg_settings'
)
select
  capability,
  value,
  source,
  case
    when capability = 'extension_available' and value <> 'true'
      then 'install an OS package that provides pg_stat_kcache before changing PostgreSQL configuration'
    when capability = 'extension_installed' and value <> 'true'
      then 'create the extension in the connected database under the site change policy'
    when capability = 'function_available' and value <> 'true'
      then 'verify the extension schema and installation integrity'
    when capability = 'delta_api_2_3' and value <> 'true'
      then 'upgrade pg_stat_kcache to 2.3 or newer so per-entry stats_since protects interval deltas'
    when capability = 'pg_stat_statements_installed' and value <> 'true'
      then 'install pg_stat_statements in the same database before pg_stat_kcache'
    when capability = 'preloaded' and value = '<hidden>'
      then 'pg_read_all_settings or pg_monitor is required to verify preload configuration'
    when capability = 'preloaded' and value <> 'true'
      then 'add pg_stat_kcache to shared_preload_libraries and restart PostgreSQL'
    when capability = 'preload_order' and value not in ('pg_stat_statements_before_pg_stat_kcache', '<hidden>')
      then 'load pg_stat_statements before pg_stat_kcache in shared_preload_libraries and restart PostgreSQL'
    when capability = 'pg_stat_kcache.track' and value = 'none'
      then 'kernel statistics collection is disabled'
    when capability = 'pg_stat_kcache.track_planning' and value <> 'on'
      then 'planning kernel counters remain zero; enable only after evaluating overhead'
    else 'ok'
  end as recommendation,
  case
    when capability in (
      'extension_available', 'extension_installed', 'function_available',
      'delta_api_2_3', 'pg_stat_statements_installed', 'preloaded'
    ) and value <> 'true' then 'unknown'
    when capability = 'preload_order'
      and value not in ('pg_stat_statements_before_pg_stat_kcache', '<hidden>') then 'unknown'
    when capability = 'pg_stat_kcache.track' and value = 'none' then 'unknown'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when capability = 'delta_api_2_3' and value <> 'true'
      then 'safe pg_stat_kcache endpoint deltas are unavailable'
    when capability = 'preload_order'
      and value not in ('pg_stat_statements_before_pg_stat_kcache', '<hidden>')
      then 'pg_stat_kcache preload prerequisites are incomplete or ordered incorrectly'
    when capability in (
      'extension_available', 'extension_installed', 'function_available',
      'pg_stat_statements_installed', 'preloaded'
    ) and value <> 'true'
      then capability || ' prerequisite is unavailable or not proven'
    when capability = 'pg_stat_kcache.track' and value = 'none'
      then 'pg_stat_kcache execution tracking is disabled'
    else ''
  end as pg_diag_internal_reason
from capabilities
order by capability
