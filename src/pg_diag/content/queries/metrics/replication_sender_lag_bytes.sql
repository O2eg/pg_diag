with senders as (
  select
    r.*,
    case
      when pg_catalog.pg_is_in_recovery() then pg_catalog.pg_last_wal_replay_lsn()
      else pg_catalog.pg_current_wal_lsn()
    end as local_wal_lsn
  from pg_catalog.pg_stat_replication r
)
select
  statement_timestamp() as snapshot_time,
  coalesce(nullif(application_name, ''), 'unnamed')
    || ' (' || coalesce(client_addr::text, 'local') || ', pid ' || pid::text || ')' as sender,
  pid,
  application_name,
  client_addr::text as client_addr,
  sync_state,
  pg_catalog.pg_wal_lsn_diff(local_wal_lsn, sent_lsn)::int8 as sent_lag_bytes,
  pg_catalog.pg_wal_lsn_diff(local_wal_lsn, flush_lsn)::int8 as flush_lag_bytes,
  pg_catalog.pg_wal_lsn_diff(local_wal_lsn, replay_lsn)::int8 as replay_lag_bytes
from senders
order by application_name, pid
limit 50
