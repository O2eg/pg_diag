select
  statement_timestamp() as snapshot_time,
  case when pg_catalog.pg_is_in_recovery() then 'standby' else 'primary' end as server_role,
  c.datid,
  c.datname,
  d.stats_reset,
  (
    coalesce(c.confl_tablespace, 0)
    + coalesce(c.confl_lock, 0)
    + coalesce(c.confl_snapshot, 0)
    + coalesce(c.confl_bufferpin, 0)
    + coalesce(c.confl_deadlock, 0)
    + coalesce((to_jsonb(c)->>'confl_active_logicalslot')::int8, 0)
  )::int8 as conflicts_total,
  c.confl_tablespace::int8 as confl_tablespace,
  c.confl_lock::int8 as confl_lock,
  c.confl_snapshot::int8 as confl_snapshot,
  c.confl_bufferpin::int8 as confl_bufferpin,
  c.confl_deadlock::int8 as confl_deadlock,
  (to_jsonb(c)->>'confl_active_logicalslot')::int8 as confl_active_logicalslot
from pg_catalog.pg_stat_database_conflicts c
left join pg_catalog.pg_stat_database d on d.datid = c.datid
order by conflicts_total desc, c.datname
