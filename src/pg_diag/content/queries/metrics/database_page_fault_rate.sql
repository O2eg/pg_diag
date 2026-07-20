select
  statement_timestamp() as snapshot_time,
  d.datname,
  min(k.stats_since) as kcache_stats_since,
  sum(k.exec_minflts)::numeric as exec_minflts,
  sum(k.exec_majflts)::numeric as exec_majflts
from pg_stat_kcache() k
join pg_database d on d.oid = k.dbid
where k.top is true
group by d.datname
order by d.datname
