select
  current_database() as datname,
  subid,
  subname,
  coalesce(worker_type, 'not_running') as worker_type,
  pid,
  leader_pid,
  case when pid is null then 0 else 1 end as worker_running,
  relid,
  case when relid is not null then relid::regclass::text end as relation_name,
  received_lsn,
  latest_end_lsn,
  case
    when received_lsn is not null and latest_end_lsn is not null
      then pg_catalog.pg_wal_lsn_diff(received_lsn, latest_end_lsn)
  end as receive_apply_lag_bytes,
  last_msg_send_time,
  last_msg_receipt_time,
  latest_end_time,
  extract(epoch from now() - last_msg_receipt_time)::bigint as seconds_since_last_msg_receipt,
  extract(epoch from now() - latest_end_time)::bigint as seconds_since_latest_end
from pg_catalog.pg_stat_subscription
order by subname, worker_type nulls first, relid nulls first;
