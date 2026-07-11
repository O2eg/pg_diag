with workers as (
  select
    current_database() as datname,
    w.subid,
    w.subname,
    s.subenabled,
    case
      when w.pid is null then 'not running'
      else coalesce(
        nullif(to_jsonb(w)->>'worker_type', ''),
        case
          when nullif(to_jsonb(w)->>'leader_pid', '') is not null then 'parallel apply'
          when w.relid is not null then 'table synchronization'
          else 'apply'
        end
      )
    end as worker_type,
    w.pid,
    nullif(to_jsonb(w)->>'leader_pid', '')::int as leader_pid,
    w.relid,
    case when w.relid is not null then w.relid::regclass::text end as relation_name,
    w.received_lsn,
    w.latest_end_lsn,
    w.last_msg_send_time,
    w.last_msg_receipt_time,
    w.latest_end_time,
    ss.apply_error_count,
    ss.sync_error_count,
    case
      when to_jsonb(ss) ? 'confl_insert_exists' then
        coalesce((to_jsonb(ss)->>'confl_insert_exists')::int8, 0)
        + coalesce((to_jsonb(ss)->>'confl_update_origin_differs')::int8, 0)
        + coalesce((to_jsonb(ss)->>'confl_update_exists')::int8, 0)
        + coalesce((to_jsonb(ss)->>'confl_update_missing')::int8, 0)
        + coalesce((to_jsonb(ss)->>'confl_delete_origin_differs')::int8, 0)
        + coalesce((to_jsonb(ss)->>'confl_delete_missing')::int8, 0)
        + coalesce((to_jsonb(ss)->>'confl_multiple_unique_conflicts')::int8, 0)
    end as conflict_count,
    ss.stats_reset as subscription_stats_reset
  from pg_catalog.pg_stat_subscription w
  join pg_catalog.pg_subscription s on s.oid = w.subid
  left join pg_catalog.pg_stat_subscription_stats ss on ss.subid = w.subid
)
select
  datname,
  subid,
  subname,
  subenabled,
  worker_type,
  pid,
  leader_pid,
  case when pid is null then 0 else 1 end as worker_running,
  relid,
  relation_name,
  received_lsn::text as received_lsn,
  latest_end_lsn::text as latest_end_lsn,
  pg_catalog.pg_wal_lsn_diff(latest_end_lsn, received_lsn)::int8
    as publisher_receive_lag_bytes,
  last_msg_send_time,
  last_msg_receipt_time,
  latest_end_time,
  round(extract(epoch from pg_catalog.clock_timestamp() - last_msg_receipt_time)::numeric, 3)
    as seconds_since_last_msg_receipt,
  round(extract(epoch from pg_catalog.clock_timestamp() - latest_end_time)::numeric, 3)
    as seconds_since_latest_end,
  apply_error_count,
  sync_error_count,
  conflict_count,
  subscription_stats_reset,
  case
    when subenabled and worker_type = 'not running' then 'medium'
    when coalesce(apply_error_count, 0) > 0 or coalesce(sync_error_count, 0) > 0
      or coalesce(conflict_count, 0) > 0 then 'medium'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when subenabled and worker_type = 'not running'
      then 'enabled subscription apply worker is not running'
    when coalesce(apply_error_count, 0) > 0 or coalesce(sync_error_count, 0) > 0
      or coalesce(conflict_count, 0) > 0
      then 'logical subscription errors or conflicts occurred since reset'
    else ''
  end as pg_diag_internal_reason
from workers
order by subname, worker_type, relid nulls first
