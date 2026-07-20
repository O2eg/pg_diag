select
  statement_timestamp() as snapshot_time,
  d.datname,
  coalesce(r.rolname, k.userid::text) as rolname,
  k.dbid,
  k.userid,
  k.top as toplevel,
  k.stats_since as kcache_stats_since,
  k.queryid::text as query_id,
  s.plans::int8 as plans,
  k.plan_user_time::numeric as plan_user_time,
  k.plan_system_time::numeric as plan_system_time,
  (k.plan_user_time + k.plan_system_time)::numeric as plan_cpu_time,
  k.plan_reads::int8 as plan_reads,
  k.plan_writes::int8 as plan_writes,
  k.plan_minflts::int8 as plan_minflts,
  k.plan_majflts::int8 as plan_majflts,
  k.plan_nvcsws::int8 as plan_nvcsws,
  k.plan_nivcsws::int8 as plan_nivcsws,
  s.query as query
from pg_stat_kcache() k
join pg_stat_statements s
  on s.dbid = k.dbid and s.userid = k.userid and s.queryid = k.queryid
join pg_database d on d.oid = k.dbid
left join pg_roles r on r.oid = k.userid
where
  d.datname = current_database()
  and k.top is true
  and current_setting('pg_stat_kcache.track_planning', true) = 'on'
order by (k.plan_user_time + k.plan_system_time) desc nulls last
limit 250
