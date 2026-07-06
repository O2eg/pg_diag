select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  schemaname,
  relname,
  heap_blks_read::int8 as heap_blks_read,
  idx_blks_read::int8 as idx_blks_read,
  (heap_blks_read + idx_blks_read + toast_blks_read + tidx_blks_read)::int8 as total_blks_read,
  (heap_blks_hit + idx_blks_hit + toast_blks_hit + tidx_blks_hit)::int8 as total_blks_hit
from pg_statio_all_tables
where schemaname not in ('pg_catalog', 'information_schema')
  and schemaname !~ '^pg_toast'
order by (heap_blks_read + idx_blks_read + toast_blks_read + tidx_blks_read) desc nulls last, schemaname, relname
limit 200
