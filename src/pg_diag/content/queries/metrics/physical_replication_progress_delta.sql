with senders as (
  select
    r.*,
    coalesce(slot.slot_type::text, 'physical') as sender_kind,
    case
      when pg_catalog.pg_is_in_recovery() then pg_catalog.pg_last_wal_replay_lsn()
      else pg_catalog.pg_current_wal_lsn()
    end as local_wal_lsn
  from pg_catalog.pg_stat_replication r
  left join pg_catalog.pg_replication_slots slot on slot.active_pid = r.pid
)
select
  statement_timestamp() as snapshot_time,
  pid,
  backend_start,
  sender_kind,
  application_name,
  client_addr::text as client_addr,
  usename,
  state,
  sync_state,
  pg_catalog.pg_wal_lsn_diff(local_wal_lsn, '0/0') as current_wal_bytes,
  pg_catalog.pg_wal_lsn_diff(sent_lsn, '0/0') as sent_bytes,
  pg_catalog.pg_wal_lsn_diff(write_lsn, '0/0') as write_bytes,
  pg_catalog.pg_wal_lsn_diff(flush_lsn, '0/0') as flush_bytes,
  pg_catalog.pg_wal_lsn_diff(replay_lsn, '0/0') as replay_bytes
from senders
order by application_name, client_addr, pid
limit 50
