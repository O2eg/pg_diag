select
  statement_timestamp() as snapshot_time,
  coalesce(nullif(application_name, ''), 'unnamed')
    || ' (' || coalesce(client_addr::text, 'local') || ', pid ' || pid::text || ')' as sender,
  pid,
  application_name,
  client_addr::text as client_addr,
  sync_state,
  extract(epoch from write_lag)::float8 as write_lag_seconds,
  extract(epoch from flush_lag)::float8 as flush_lag_seconds,
  extract(epoch from replay_lag)::float8 as replay_lag_seconds
from pg_catalog.pg_stat_replication
order by application_name, pid
limit 50
