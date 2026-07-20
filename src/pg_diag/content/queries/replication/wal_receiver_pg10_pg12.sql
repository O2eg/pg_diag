select
  current_database() as datname,
  pid,
  status,
  receive_start_lsn::text as receive_start_lsn,
  receive_start_tli,
  null::text as written_lsn,
  received_lsn::text as flushed_lsn,
  received_tli,
  latest_end_lsn::text as latest_end_lsn,
  pg_catalog.pg_wal_lsn_diff(latest_end_lsn, received_lsn)::int8 as receive_lag_bytes,
  last_msg_send_time,
  last_msg_receipt_time,
  latest_end_time,
  extract(epoch from pg_catalog.clock_timestamp() - last_msg_receipt_time)::numeric
    as seconds_since_last_message,
  extract(epoch from pg_catalog.clock_timestamp() - latest_end_time)::numeric
    as seconds_since_latest_end,
  sender_host,
  sender_port,
  slot_name,
  case when status = 'streaming' then 'ok' else 'medium' end
    as pg_diag_internal_severity,
  case when status = 'streaming' then '' else 'WAL receiver is not streaming' end
    as pg_diag_internal_reason
from pg_catalog.pg_stat_wal_receiver
order by seconds_since_last_message desc nulls last, pid
