select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  relid,
  schemaname,
  relname,
  idx_blks_read::int8 as idx_blks_read
from pg_statio_all_tables
where schemaname not in ('pg_catalog', 'information_schema')
  and schemaname !~ '^pg_toast'
order by idx_blks_read desc nulls last, schemaname, relname
limit 200
