select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  coalesce(backend_type, 'total') as backend_type,
  sum(coalesce(reads, 0) * op_bytes)::int8 as read_bytes,
  sum(coalesce(writes, 0) * op_bytes)::int8 as write_bytes
from pg_stat_io
group by rollup (backend_type)
