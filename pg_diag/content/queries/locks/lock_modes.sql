select
  current_database() as datname,
  locks.locktype,
  locks.mode,
  locks.granted,
  count(*)::int8 as locks,
  case when locks.granted then 'ok' else 'medium' end as pg_diag_internal_severity,
  case
    when locks.granted then ''
    else 'One or more lock requests are currently waiting'
  end as pg_diag_internal_reason
from pg_locks locks
left join pg_stat_activity activity on activity.pid = locks.pid
where
  locks.pid is distinct from pg_backend_pid()
  and (
    locks.database = (select oid from pg_database where datname = current_database())
    or activity.datname = current_database()
  )
group by 1, 2, 3, 4
order by locks desc, locktype asc, mode asc, granted desc
