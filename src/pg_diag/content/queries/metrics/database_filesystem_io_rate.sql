select
  statement_timestamp() as snapshot_time,
  d.datname,
  min(k.stats_since) as kcache_stats_since,
  sum(k.exec_reads)::numeric as exec_reads,
  sum(k.exec_writes)::numeric as exec_writes
from pg_stat_kcache() k
join pg_database d on d.oid = k.dbid
where k.top is true
group by d.datname
order by d.datname
