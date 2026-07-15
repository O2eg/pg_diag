select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  io.relid,
  schemaname,
  relname,
  db.stats_reset,
  heap_blks_read::int8 as heap_blks_read,
  heap_blks_hit::int8 as heap_blks_hit,
  idx_blks_read::int8 as idx_blks_read,
  idx_blks_hit::int8 as idx_blks_hit,
  toast_blks_read::int8 as toast_blks_read,
  toast_blks_hit::int8 as toast_blks_hit,
  tidx_blks_read::int8 as tidx_blks_read,
  tidx_blks_hit::int8 as tidx_blks_hit,
  (heap_blks_read + idx_blks_read + toast_blks_read + tidx_blks_read)::int8 as total_blks_read,
  (heap_blks_hit + idx_blks_hit + toast_blks_hit + tidx_blks_hit)::int8 as total_blks_hit,
  (
    (heap_blks_hit + idx_blks_hit + toast_blks_hit + tidx_blks_hit)::numeric * 100.0
    / nullif(heap_blks_hit + idx_blks_hit + toast_blks_hit + tidx_blks_hit + heap_blks_read + idx_blks_read + toast_blks_read + tidx_blks_read, 0)) as cache_hit_pct
from pg_statio_all_tables io
left join pg_stat_database db on db.datname = current_database()
where schemaname not in ('pg_catalog', 'information_schema')
  and schemaname !~ '^pg_toast'
order by total_blks_read desc nulls last, schemaname, relname, io.relid
limit 200
