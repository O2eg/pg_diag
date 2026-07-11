with database_conflicts as (
  select
    case when pg_catalog.pg_is_in_recovery() then 'standby' else 'primary' end as server_role,
    c.datid,
    c.datname,
    d.stats_reset,
    c.confl_tablespace,
    c.confl_lock,
    c.confl_snapshot,
    c.confl_bufferpin,
    c.confl_deadlock,
    c.confl_active_logicalslot,
    (
      coalesce(confl_tablespace, 0)
      + coalesce(confl_lock, 0)
      + coalesce(confl_snapshot, 0)
      + coalesce(confl_bufferpin, 0)
      + coalesce(confl_deadlock, 0)
      + coalesce(confl_active_logicalslot, 0)
    ) as conflicts_total
  from pg_catalog.pg_stat_database_conflicts c
  left join pg_catalog.pg_stat_database d on d.datid = c.datid
)
select
  server_role,
  datname,
  datid,
  stats_reset,
  conflicts_total,
  confl_tablespace,
  confl_lock,
  confl_snapshot,
  confl_bufferpin,
  confl_deadlock,
  confl_active_logicalslot,
  case when conflicts_total > 0 then 'medium' else 'ok' end
    as pg_diag_internal_severity,
  case when conflicts_total > 0 then 'standby recovery conflicts occurred since reset' else '' end
    as pg_diag_internal_reason
from database_conflicts
order by conflicts_total desc, datname;
