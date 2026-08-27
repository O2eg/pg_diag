with recovery as (
  select
    pg_catalog.pg_is_in_recovery() as in_recovery,
    case when pg_catalog.pg_is_in_recovery() then pg_catalog.pg_last_wal_receive_lsn() end as receive_lsn,
    case when pg_catalog.pg_is_in_recovery() then pg_catalog.pg_last_wal_replay_lsn() end as replay_lsn,
    case when pg_catalog.pg_is_in_recovery() then pg_catalog.pg_last_xact_replay_timestamp() end as last_replayed_xact_time,
    case when pg_catalog.pg_is_in_recovery() then pg_catalog.pg_get_wal_replay_pause_state() else 'not in recovery' end as replay_pause_state
),
receiver as (
  select
    w.status as wal_receiver_status,
    w.slot_name as wal_receiver_slot_name,
    w.conninfo as receiver_conninfo
  from pg_catalog.pg_stat_wal_receiver w
  limit 1
),
settings as (
  select
    nullif(current_setting('primary_conninfo', true), '') as primary_conninfo_setting,
    nullif(current_setting('primary_slot_name', true), '') as primary_slot_name,
    current_setting('recovery_min_apply_delay', true) as recovery_min_apply_delay,
    current_setting('recovery_target_timeline', true) as recovery_target_timeline,
    (coalesce(current_setting('restore_command', true), '') <> '') as restore_command_configured,
    current_setting('hot_standby')::boolean as hot_standby,
    current_setting('hot_standby_feedback')::boolean as hot_standby_feedback,
    current_setting('max_standby_streaming_delay') as max_standby_streaming_delay,
    current_setting('max_standby_archive_delay') as max_standby_archive_delay,
    current_setting('wal_receiver_timeout') as wal_receiver_timeout,
    current_setting('wal_receiver_status_interval') as wal_receiver_status_interval,
    current_setting('wal_retrieve_retry_interval') as wal_retrieve_retry_interval
),
control as (
  select
    cp.timeline_id::int8 as timeline,
    cr.min_recovery_end_lsn::text as min_recovery_end_lsn,
    cr.min_recovery_end_timeline::int8 as min_recovery_end_timeline,
    cr.end_of_backup_record_required
  from pg_catalog.pg_control_checkpoint() cp
  cross join pg_catalog.pg_control_recovery() cr
),
conninfo as (
  select coalesce(s.primary_conninfo_setting, r.receiver_conninfo) as ci
  from settings s
  left join receiver r on true
),
primary_target as (
  select
    trim(both '''"' from coalesce(
      substring(ci from '(?:^|\s)host=([^\s]+)'),
      substring(ci from '://(?:[^@/\s]*@)?([^:/?\s]+)')
    )) as primary_host,
    trim(both '''"' from coalesce(
      substring(ci from '(?:^|\s)port=(\d+)'),
      substring(ci from '://(?:[^@/\s]*@)?[^:/?\s]+:(\d+)')
    )) as primary_port,
    trim(both '''"' from coalesce(
      substring(ci from '(?:^|\s)user=([^\s]+)'),
      substring(ci from '://([^:@/\s]+)(?::[^@\s]*)?@')
    )) as primary_user,
    trim(both '''"' from coalesce(
      substring(ci from '(?:^|\s)sslmode=([^\s]+)'),
      substring(ci from '[?&]sslmode=([^&\s]+)')
    )) as primary_sslmode,
    trim(both '''"' from coalesce(
      substring(ci from '(?:^|\s)application_name=([^\s]+)'),
      substring(ci from '[?&]application_name=([^&\s]+)')
    )) as primary_application_name,
    (ci is not null) as primary_target_configured
  from conninfo
)
select
  case when rc.in_recovery then 'standby' else 'primary' end as server_role,
  rc.in_recovery,
  rc.replay_pause_state,
  (rc.replay_pause_state in ('paused', 'pause requested')) as replay_paused,
  rc.receive_lsn::text as receive_lsn,
  rc.replay_lsn::text as replay_lsn,
  pg_catalog.pg_wal_lsn_diff(rc.receive_lsn, rc.replay_lsn)::int8 as receive_replay_lag_bytes,
  rc.last_replayed_xact_time,
  extract(epoch from pg_catalog.clock_timestamp() - rc.last_replayed_xact_time)::float8
    as seconds_since_last_replayed_xact,
  c.timeline,
  c.min_recovery_end_lsn,
  c.min_recovery_end_timeline,
  c.end_of_backup_record_required,
  r.wal_receiver_status,
  r.wal_receiver_slot_name,
  s.primary_slot_name,
  pt.primary_target_configured,
  pt.primary_host,
  pt.primary_port,
  pt.primary_user,
  pt.primary_sslmode,
  pt.primary_application_name,
  s.recovery_min_apply_delay,
  s.recovery_target_timeline,
  s.restore_command_configured,
  s.hot_standby,
  s.hot_standby_feedback,
  s.max_standby_streaming_delay,
  s.max_standby_archive_delay,
  s.wal_receiver_timeout,
  s.wal_receiver_status_interval,
  s.wal_retrieve_retry_interval,
  case
    when rc.in_recovery and rc.replay_pause_state in ('paused', 'pause requested') then 'high'
    when rc.in_recovery and r.wal_receiver_status is not null
      and coalesce(nullif(coalesce(s.primary_slot_name, r.wal_receiver_slot_name), ''), '') = ''
      then 'medium'
    when rc.in_recovery and not s.hot_standby_feedback then 'unknown'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when rc.in_recovery and rc.replay_pause_state in ('paused', 'pause requested')
      then 'WAL replay is paused; the standby falls behind until pg_wal_replay_resume() is called'
    when rc.in_recovery and r.wal_receiver_status is not null
      and coalesce(nullif(coalesce(s.primary_slot_name, r.wal_receiver_slot_name), ''), '') = ''
      then 'Streaming without a replication slot; WAL retention on the primary depends on wal_keep_size only'
    when rc.in_recovery and not s.hot_standby_feedback
      then 'hot_standby_feedback is off; long standby queries can be cancelled by recovery conflicts'
    else ''
  end as pg_diag_internal_reason
from recovery rc
cross join settings s
cross join control c
cross join primary_target pt
left join receiver r on true
