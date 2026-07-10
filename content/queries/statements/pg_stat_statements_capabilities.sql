with settings as (
  select name, setting
  from pg_settings
  where name in (
    'shared_preload_libraries',
    'compute_query_id',
    'track_io_timing',
    'pg_stat_statements.max',
    'pg_stat_statements.save',
    'pg_stat_statements.track',
    'pg_stat_statements.track_planning',
    'pg_stat_statements.track_utility'
  )
),
required_columns(column_name) as (
  select unnest(
    array[
      'userid', 'dbid', 'toplevel', 'queryid', 'query', 'calls',
      'total_exec_time', 'mean_exec_time', 'max_exec_time', 'total_plan_time',
      'rows', 'shared_blks_hit', 'shared_blks_read', 'shared_blks_dirtied',
      'shared_blks_written', 'temp_blks_read', 'temp_blks_written',
      'wal_records', 'wal_fpi', 'wal_bytes'
    ]::text[]
    || case
      when current_setting('server_version_num')::int >= 170000
        then array['shared_blk_read_time', 'shared_blk_write_time', 'stats_since', 'minmax_stats_since']
      else array['blk_read_time', 'blk_write_time']
    end
    || case
      when current_setting('server_version_num')::int >= 180000
        then array['parallel_workers_to_launch', 'parallel_workers_launched']
      else array[]::text[]
    end
  )
),
role_access as (
  select
    coalesce((select rolsuper from pg_roles where rolname = current_user), false) as is_superuser,
    pg_has_role(current_user, 'pg_read_all_stats', 'member') as has_read_all_stats,
    pg_has_role(current_user, 'pg_read_all_settings', 'member') as has_read_all_settings
),
capabilities as (
  select
    'extension_available'::text as capability,
    exists (select 1 from pg_available_extensions where name = 'pg_stat_statements')::text as value,
    'pg_available_extensions'::text as source
  union all
  select
    'extension_installed',
    exists (select 1 from pg_extension where extname = 'pg_stat_statements')::text,
    'pg_extension'
  union all
  select
    'extension_version',
    coalesce((select extversion from pg_extension where extname = 'pg_stat_statements'), '<not installed>'),
    'pg_extension'
  union all
  select
    'extension_schema',
    coalesce(
      (
        select namespace.nspname
        from pg_extension extension
        join pg_namespace namespace on namespace.oid = extension.extnamespace
        where extension.extname = 'pg_stat_statements'
      ),
      '<not installed>'
    ),
    'pg_extension'
  union all
  select
    'view_available',
    (to_regclass('pg_stat_statements') is not null)::text,
    'to_regclass on pg_diag search_path'
  union all
  select
    'info_view_available',
    (to_regclass('pg_stat_statements_info') is not null)::text,
    'to_regclass on pg_diag search_path'
  union all
  select
    'required_view_columns',
    (
      to_regclass('pg_stat_statements') is not null
      and not exists (
        select 1
        from required_columns required
        where not exists (
          select 1
          from pg_attribute attribute
          where
            attribute.attrelid = to_regclass('pg_stat_statements')
            and attribute.attname = required.column_name
            and attribute.attnum > 0
            and not attribute.attisdropped
        )
      )
    )::text,
    'pg_attribute'
  union all
  select
    'preloaded',
    case
      when (select setting from settings where name = 'shared_preload_libraries') is null
        then '<hidden>'
      else exists (
        select 1
        from regexp_split_to_table(
          (select setting from settings where name = 'shared_preload_libraries'),
          ','
        ) as library(name)
        where btrim(library.name) = 'pg_stat_statements'
      )::text
    end,
    'shared_preload_libraries'
  union all
  select
    'compute_query_id',
    coalesce((select setting from settings where name = 'compute_query_id'), '<missing>'),
    'pg_settings'
  union all
  select
    'cross_user_query_visibility',
    case
      when access.is_superuser or access.has_read_all_stats then 'full'
      else 'current_user_only'
    end,
    'role membership'
  from role_access access
  union all
  select
    'settings_visibility',
    case
      when access.is_superuser or access.has_read_all_settings then 'full'
      else 'restricted'
    end,
    'role membership'
  from role_access access
  union all
  select
    'track_io_timing',
    coalesce((select setting from settings where name = 'track_io_timing'), '<missing>'),
    'pg_settings'
  union all
  select
    'pg_stat_statements.max',
    coalesce((select setting from settings where name = 'pg_stat_statements.max'), '<missing>'),
    'pg_settings'
  union all
  select
    'pg_stat_statements.save',
    coalesce((select setting from settings where name = 'pg_stat_statements.save'), '<missing>'),
    'pg_settings'
  union all
  select
    'pg_stat_statements.track',
    coalesce((select setting from settings where name = 'pg_stat_statements.track'), '<missing>'),
    'pg_settings'
  union all
  select
    'pg_stat_statements.track_planning',
    coalesce((select setting from settings where name = 'pg_stat_statements.track_planning'), '<missing>'),
    'pg_settings'
  union all
  select
    'pg_stat_statements.track_utility',
    coalesce((select setting from settings where name = 'pg_stat_statements.track_utility'), '<missing>'),
    'pg_settings'
)
select
  capability,
  value,
  source,
  case
    when capability = 'extension_available' and value <> 'true'
      then 'the pg_stat_statements package is not available on this server'
    when capability = 'extension_installed' and value <> 'true'
      then 'install the extension in this database under the site change policy'
    when capability in ('view_available', 'info_view_available') and value <> 'true'
      then 'the extension view is unavailable in the current database or pg_diag search path'
    when capability = 'required_view_columns' and value <> 'true'
      then 'required columns are unavailable; install or update the extension as indicated by the other capability rows'
    when capability = 'preloaded' and value = '<hidden>'
      then 'shared_preload_libraries is hidden; pg_read_all_settings or pg_monitor is required to verify preload'
    when capability = 'preloaded' and value <> 'true'
      then 'add pg_stat_statements to shared_preload_libraries and restart PostgreSQL'
    when capability = 'compute_query_id' and value not in ('on', 'auto')
      then 'query identifiers require compute_query_id=on/auto or another query-ID provider'
    when capability = 'cross_user_query_visibility' and value <> 'full'
      then 'Top SQL can identify only statements owned by the current role; grant pg_read_all_stats only if policy permits'
    when capability = 'settings_visibility' and value <> 'full'
      then 'some configuration evidence is hidden; grant pg_read_all_settings only if policy permits'
    when capability = 'track_io_timing' and value <> 'on'
      then 'block counts remain valid, but statement I/O timing columns stay zero'
    when capability = 'pg_stat_statements.track' and value = 'none'
      then 'statement statistics collection is disabled'
    when capability = 'pg_stat_statements.track_planning' and value <> 'on'
      then 'planning counters stay zero; enabling planning tracking can add contention overhead'
    when capability = 'pg_stat_statements.track_utility' and value <> 'on'
      then 'utility commands are not included in statement statistics'
    else 'ok'
  end as recommendation,
  case
    when capability in (
      'extension_available', 'extension_installed', 'view_available',
      'info_view_available', 'required_view_columns', 'preloaded'
    ) and value <> 'true' then 'unknown'
    when capability = 'compute_query_id' and value not in ('on', 'auto') then 'unknown'
    when capability = 'cross_user_query_visibility' and value <> 'full' then 'unknown'
    when capability = 'settings_visibility' and value <> 'full' then 'unknown'
    when capability = 'pg_stat_statements.track' and value = 'none' then 'unknown'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when capability = 'extension_available' and value <> 'true'
      then 'pg_stat_statements package availability is not proven'
    when capability = 'extension_installed' and value <> 'true'
      then 'pg_stat_statements is not installed in the connected database'
    when capability in ('view_available', 'info_view_available') and value <> 'true'
      then capability || ' is false'
    when capability = 'required_view_columns' and value <> 'true'
      then 'columns required by the selected PostgreSQL variant are unavailable'
    when capability = 'preloaded' and value = '<hidden>'
      then 'shared_preload_libraries is not visible to the collection role'
    when capability = 'preloaded' and value <> 'true'
      then 'pg_stat_statements is not present in shared_preload_libraries'
    when capability = 'compute_query_id' and value not in ('on', 'auto')
      then 'built-in query ID computation is not enabled'
    when capability = 'cross_user_query_visibility' and value <> 'full'
      then 'query IDs and SQL text for other roles are hidden'
    when capability = 'settings_visibility' and value <> 'full'
      then 'some pg_stat_statements configuration evidence is hidden'
    when capability = 'pg_stat_statements.track' and value = 'none'
      then 'pg_stat_statements tracking is disabled'
    else ''
  end as pg_diag_internal_reason
from capabilities
order by capability
