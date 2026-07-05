select
  p.datname,
  p.pid,
  p.relid::regclass::text as relation,
  p.cluster_index_relid::regclass::text as index_name,
  a.state,
  coalesce(a.wait_event_type || '.' || a.wait_event, '') as waiting,
  p.phase,
  p.heap_blks_total * current_setting('block_size')::int8 as total_bytes,
  p.heap_blks_scanned * current_setting('block_size')::int8 as scanned_bytes,
  round(p.heap_blks_scanned::numeric * 100 / nullif(p.heap_blks_total, 0), 3) as scanned_pct,
  coalesce(p.heap_tuples_scanned, 0) as tuples_scanned,
  coalesce(p.heap_tuples_written, 0) as tuples_written,
  extract(epoch from clock_timestamp() - a.xact_start)::numeric(20, 3) as xact_age_seconds,
  left(regexp_replace(coalesce(a.query, ''), '\s+', ' ', 'g'), 500) as query
from pg_stat_progress_cluster p
join pg_stat_activity a on p.pid = a.pid
where a.pid <> pg_backend_pid()
order by xact_age_seconds desc
