select
  statement_timestamp() as snapshot_time,
  d.datname,
  min(k.stats_since) as kcache_stats_since,
  sum(k.exec_user_time)::numeric as exec_user_time,
  sum(k.exec_system_time)::numeric as exec_system_time
from pg_stat_kcache() k
join pg_database d on d.oid = k.dbid
where k.top is true
group by d.datname
order by d.datname
