select
  current_database() as datname,
  mode,
  granted,
  count(*)::int8 as locks
from pg_locks
where database = (select oid from pg_database where datname = current_database())
group by 1, 2, 3
order by locks desc, mode asc, granted desc
