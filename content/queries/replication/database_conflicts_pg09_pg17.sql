with database_conflicts as (
  select
    case when pg_catalog.pg_is_in_recovery() then 'standby' else 'primary' end as server_role,
    datid,
    datname,
    confl_tablespace,
    confl_lock,
    confl_snapshot,
    confl_bufferpin,
    confl_deadlock,
    (
      coalesce(confl_tablespace, 0)
      + coalesce(confl_lock, 0)
      + coalesce(confl_snapshot, 0)
      + coalesce(confl_bufferpin, 0)
      + coalesce(confl_deadlock, 0)
    ) as conflicts_total
  from pg_catalog.pg_stat_database_conflicts
)
select
  server_role,
  datname,
  datid,
  conflicts_total,
  confl_tablespace,
  confl_lock,
  confl_snapshot,
  confl_bufferpin,
  confl_deadlock
from database_conflicts
order by conflicts_total desc, datname;
