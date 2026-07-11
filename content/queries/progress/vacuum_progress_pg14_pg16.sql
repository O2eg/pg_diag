select
  p.datid,
  p.datname,
  p.relid,
  n.nspname as schemaname,
  c.relname as relname,
  p.pid,
  a.backend_type,
  case
    when a.backend_type = 'autovacuum worker'
      and a.query ~* 'to prevent wraparound' then 'aggressive_autovacuum'
    when a.backend_type = 'autovacuum worker' then 'autovacuum'
    when a.query ~* '^vacuum' then 'manual_vacuum'
    else 'unknown'
  end as vacuum_mode,
  a.state,
  coalesce(a.wait_event_type || '.' || a.wait_event, '') as waiting,
  p.phase,
  case
    when p.heap_blks_total = 0 then null
    else round(p.heap_blks_scanned::numeric * 100 / p.heap_blks_total, 3)
  end as heap_scanned_pct,
  case
    when p.heap_blks_total = 0 then null
    else round(p.heap_blks_vacuumed::numeric * 100 / p.heap_blks_total, 3)
  end as heap_vacuumed_pct,
  p.heap_blks_total,
  p.heap_blks_scanned,
  p.heap_blks_vacuumed,
  p.index_vacuum_count,
  p.max_dead_tuples,
  p.num_dead_tuples,
  extract(epoch from clock_timestamp() - a.query_start)::numeric(20, 3) as query_age_seconds,
  case
    when a.backend_type <> 'autovacuum worker' then false
    when a.query is null or a.query like '<%' then null
    else a.query ~* 'to prevent wraparound'
  end as anti_wraparound,
  left(regexp_replace(coalesce(a.query, ''), '\s+', ' ', 'g'), 500) as query
from pg_catalog.pg_stat_progress_vacuum p
join pg_catalog.pg_stat_activity a on a.pid = p.pid
join pg_catalog.pg_class c on c.oid = p.relid
join pg_catalog.pg_namespace n on n.oid = c.relnamespace
where p.datid = (select oid from pg_catalog.pg_database where datname = current_database())
  and p.pid <> pg_catalog.pg_backend_pid()
order by query_age_seconds desc
