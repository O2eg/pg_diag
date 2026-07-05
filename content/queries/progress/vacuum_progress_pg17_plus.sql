select
  p.datname,
  n.nspname as schemaname,
  c.relname as relname,
  p.pid,
  case
    when a.query ~ '^autovacuum.*(to prevent wraparound)' then 'aggressive_autovacuum'
    when a.query ~ '^autovacuum' then 'autovacuum'
    when a.query ~* '^vacuum' then 'manual_vacuum'
    else 'unknown'
  end as vacuum_mode,
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
  p.max_dead_tuple_bytes,
  p.num_dead_item_ids,
  extract(epoch from clock_timestamp() - a.query_start)::numeric(20, 3) as query_age_seconds,
  (a.backend_xid is not null) as anti_wraparound,
  left(regexp_replace(coalesce(a.query, ''), '\s+', ' ', 'g'), 500) as query
from pg_stat_progress_vacuum p
join pg_stat_activity a on a.pid = p.pid
join pg_class c on c.oid = p.relid
join pg_namespace n on n.oid = c.relnamespace
where p.datname = current_database()
order by query_age_seconds desc
