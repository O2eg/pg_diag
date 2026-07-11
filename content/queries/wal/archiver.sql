with settings as (
  select
    pg_catalog.pg_size_bytes(current_setting('wal_segment_size')) as wal_segment_size_bytes,
    current_setting('archive_mode') as archive_mode,
    current_setting('archive_command') as archive_command,
    current_setting('archive_library', true) as archive_library
),
current_wal as (
  select
    pg_catalog.pg_is_in_recovery() as in_recovery,
    case
      when not pg_catalog.pg_is_in_recovery()
        then pg_catalog.pg_walfile_name(pg_catalog.pg_current_wal_lsn())
    end as current_wal_file
),
archive_state as (
  select
    a.*,
    s.*,
    w.in_recovery,
    w.current_wal_file,
    a.last_archived_wal ~ '^[0-9A-F]{24}$' as archived_name_is_segment,
    w.current_wal_file ~ '^[0-9A-F]{24}$' as current_name_is_segment
  from pg_catalog.pg_stat_archiver a
  cross join settings s
  cross join current_wal w
)
select
  case when in_recovery then 'standby' else 'primary' end as server_role,
  archive_mode,
  archive_mode <> 'off'
    and (
      coalesce(nullif(archive_command, ''), '(disabled)') not in ('(disabled)', '(none)')
      or coalesce(nullif(archive_library, ''), '(disabled)') not in ('(disabled)', '(none)')
    ) as archive_target_configured,
  archived_count,
  failed_count,
  last_archived_wal,
  last_archived_time,
  last_failed_wal,
  last_failed_time,
  current_wal_file,
  wal_segment_size_bytes,
  case
    when archived_name_is_segment
      and current_name_is_segment
      and substr(current_wal_file, 1, 8) = substr(last_archived_wal, 1, 8)
    then
      (
        ('x' || substr(current_wal_file, 9, 8))::bit(32)::bigint
        - ('x' || substr(last_archived_wal, 9, 8))::bit(32)::bigint
      ) * (4294967296::bigint / wal_segment_size_bytes)
      + (
        ('x' || substr(current_wal_file, 17, 8))::bit(32)::bigint
        - ('x' || substr(last_archived_wal, 17, 8))::bit(32)::bigint
      )
  end as segments_ahead_of_last_archived_same_timeline,
  case
    when archived_name_is_segment and current_name_is_segment
      then substr(current_wal_file, 1, 8) <> substr(last_archived_wal, 1, 8)
  end as archive_timeline_changed,
  stats_reset,
  case
    when archive_mode <> 'off'
      and coalesce(nullif(archive_command, ''), '(disabled)') in ('(disabled)', '(none)')
      and coalesce(nullif(archive_library, ''), '(disabled)') in ('(disabled)', '(none)')
      then 'medium'
    when last_failed_time is not null
      and (last_archived_time is null or last_failed_time > last_archived_time) then 'medium'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when archive_mode <> 'off'
      and coalesce(nullif(archive_command, ''), '(disabled)') in ('(disabled)', '(none)')
      and coalesce(nullif(archive_library, ''), '(disabled)') in ('(disabled)', '(none)')
      then 'archive_mode is enabled but no archive command or library is configured'
    when last_failed_time is not null
      and (last_archived_time is null or last_failed_time > last_archived_time)
      then 'the latest recorded archive attempt failed'
    else ''
  end as pg_diag_internal_reason
from archive_state
