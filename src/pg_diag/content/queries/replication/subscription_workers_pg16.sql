with workers as (
  select
    current_database() as datname,
    s.oid as subid,
    s.subname,
    s.subenabled,
    case
      when w.pid is null then 'not running'
      when w.leader_pid is not null then 'parallel apply'
      when w.relid is not null then 'table synchronization'
      else 'apply'
    end as worker_type,
    w.pid,
    w.leader_pid,
    w.relid,
    case when w.relid is not null then w.relid::regclass::text end as relation_name,
    w.received_lsn,
    w.latest_end_lsn,
    w.last_msg_send_time,
    w.last_msg_receipt_time,
    w.latest_end_time,
    ss.apply_error_count,
    ss.sync_error_count,
    null::int8 as conflict_count,
    ss.stats_reset as subscription_stats_reset
  from pg_catalog.pg_subscription s
  left join pg_catalog.pg_stat_subscription w on w.subid = s.oid
  left join pg_catalog.pg_stat_subscription_stats ss on ss.subid = s.oid
)
select
  datname,
  subid,
  subname,
  subenabled,
  worker_type,
  pid,
  leader_pid,
  (pid is not null) as worker_running,
  relid,
  relation_name,
  received_lsn::text as received_lsn,
  latest_end_lsn::text as latest_end_lsn,
  pg_catalog.pg_wal_lsn_diff(latest_end_lsn, received_lsn)::int8
    as publisher_receive_lag_bytes,
  last_msg_send_time,
  last_msg_receipt_time,
  latest_end_time,
  (extract(epoch from pg_catalog.clock_timestamp() - last_msg_receipt_time)::numeric)
    as seconds_since_last_msg_receipt,
  (extract(epoch from pg_catalog.clock_timestamp() - latest_end_time)::numeric)
    as seconds_since_latest_end,
  apply_error_count,
  sync_error_count,
  conflict_count,
  subscription_stats_reset,
  case
    when subenabled and pid is null then 'medium'
    when apply_error_count > 0 or sync_error_count > 0 then 'medium'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when subenabled and pid is null then 'enabled subscription apply worker is not running'
    when apply_error_count > 0 or sync_error_count > 0
      then 'logical subscription errors occurred since reset'
    else ''
  end as pg_diag_internal_reason
from workers
order by subname, worker_type, relid nulls first
