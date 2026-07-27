with lock_rows as (
  select
    locks.locktype,
    locks.mode,
    locks.granted,
    locks.pid,
    case
      when locked_relation.oid is not null
        then format('%I.%I', relation_namespace.nspname, locked_relation.relname)
    end as relation_name
  from pg_locks locks
  left join pg_stat_activity activity on activity.pid = locks.pid
  left join pg_class locked_relation on locked_relation.oid = locks.relation
  left join pg_namespace relation_namespace
    on relation_namespace.oid = locked_relation.relnamespace
  where
    locks.pid is distinct from pg_backend_pid()
    and (
      locks.database = (select oid from pg_database where datname = current_database())
      or activity.datname = current_database()
    )
)
select
  current_database() as datname,
  lock_rows.locktype,
  lock_rows.mode,
  lock_rows.granted,
  count(*)::int8 as locks,
  coalesce(
    ((array_agg(distinct lock_rows.pid order by lock_rows.pid)
      filter (where lock_rows.pid is not null)))[1:50],
    array[]::integer[]
  ) as backend_pids,
  coalesce(
    ((array_agg(distinct lock_rows.relation_name order by lock_rows.relation_name)
      filter (where lock_rows.relation_name is not null)))[1:50],
    array[]::text[]
  ) as relations,
  case when lock_rows.granted then 'ok' else 'medium' end as pg_diag_internal_severity,
  case
    when lock_rows.granted then ''
    else 'One or more lock requests are currently waiting'
  end as pg_diag_internal_reason
from lock_rows
group by 1, 2, 3, 4
order by locks desc, locktype asc, mode asc, granted desc
