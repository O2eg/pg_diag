with wal_context as (
  select
    pg_catalog.pg_is_in_recovery() as in_recovery,
    case
      when not pg_catalog.pg_is_in_recovery() then pg_catalog.pg_current_wal_insert_lsn()
    end as insert_lsn,
    case
      when not pg_catalog.pg_is_in_recovery() then pg_catalog.pg_current_wal_lsn()
    end as write_lsn,
    case
      when not pg_catalog.pg_is_in_recovery() then pg_catalog.pg_current_wal_flush_lsn()
    end as flush_lsn,
    case
      when pg_catalog.pg_is_in_recovery() then pg_catalog.pg_last_wal_receive_lsn()
    end as receive_lsn,
    case
      when pg_catalog.pg_is_in_recovery() then pg_catalog.pg_last_wal_replay_lsn()
    end as replay_lsn
)
select
  current_database() as datname,
  case when w.in_recovery then 'standby' else 'primary' end as server_role,
  w.in_recovery,
  coalesce(w.replay_lsn, w.write_lsn)::text as current_wal_lsn,
  w.insert_lsn::text as insert_lsn,
  w.write_lsn::text as write_lsn,
  w.flush_lsn::text as flush_lsn,
  w.receive_lsn::text as receive_lsn,
  w.replay_lsn::text as replay_lsn,
  pg_catalog.pg_wal_lsn_diff(w.receive_lsn, w.replay_lsn)::int8 as receive_replay_lag_bytes,
  pg_catalog.pg_last_xact_replay_timestamp() as last_replayed_xact_time,
  (
    extract(epoch from pg_catalog.clock_timestamp() - pg_catalog.pg_last_xact_replay_timestamp())::numeric) as seconds_since_last_replayed_xact,
  pg_catalog.pg_wal_lsn_diff(coalesce(w.replay_lsn, w.write_lsn), '0/0')::int8
    as xlog_location_b,
  extract(epoch from (now() - pg_catalog.pg_postmaster_start_time()))::int8
    as postmaster_uptime_s,
  c.system_identifier::text as sys_id,
  cp.timeline_id::int as timeline
from wal_context w
cross join pg_catalog.pg_control_system() c
cross join pg_catalog.pg_control_checkpoint() cp
