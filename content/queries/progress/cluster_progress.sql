select
  p.datid,
  p.datname,
  p.relid,
  case when p.relid <> 0 then p.relid::regclass::text end as relation,
  p.cluster_index_relid,
  case
    when p.cluster_index_relid <> 0 then p.cluster_index_relid::regclass::text
  end as index_name,
  p.pid,
  p.command,
  a.state,
  coalesce(a.wait_event_type || '.' || a.wait_event, '') as waiting,
  p.phase,
  p.heap_blks_total * current_setting('block_size')::int8 as total_bytes,
  p.heap_blks_scanned * current_setting('block_size')::int8 as scanned_bytes,
  (p.heap_blks_scanned::numeric * 100 / nullif(p.heap_blks_total, 0)) as scanned_pct,
  p.heap_tuples_scanned as tuples_scanned,
  p.heap_tuples_written as tuples_written,
  p.index_rebuild_count,
  extract(epoch from clock_timestamp() - a.query_start)::numeric as query_age_seconds,
  left(regexp_replace(coalesce(a.query, ''), '\s+', ' ', 'g'), 500) as query
from pg_catalog.pg_stat_progress_cluster p
join pg_catalog.pg_stat_activity a on p.pid = a.pid
where p.datid = (select oid from pg_catalog.pg_database where datname = current_database())
  and a.pid <> pg_catalog.pg_backend_pid()
order by query_age_seconds desc
