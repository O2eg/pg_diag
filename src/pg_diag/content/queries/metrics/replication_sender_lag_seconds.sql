select
  statement_timestamp() as snapshot_time,
  coalesce(nullif(r.application_name, ''), 'unnamed')
    || case when slot.slot_type = 'logical' then ' [logical]' else '' end
    || ' (' || coalesce(r.client_addr::text, 'local') || ', pid ' || r.pid::text || ')' as sender,
  r.pid,
  r.application_name,
  r.client_addr::text as client_addr,
  r.sync_state,
  extract(epoch from r.write_lag)::float8 as write_lag_seconds,
  extract(epoch from r.flush_lag)::float8 as flush_lag_seconds,
  extract(epoch from r.replay_lag)::float8 as replay_lag_seconds
from pg_catalog.pg_stat_replication r
left join pg_catalog.pg_replication_slots slot on slot.active_pid = r.pid
order by r.application_name, r.pid
limit 50
