select
  statement_timestamp() as snapshot_time,
  'cluster'::text as scope,
  backend_type,
  sum(reads * op_bytes)::int8 as read_bytes,
  sum(writes * op_bytes)::int8 as write_bytes
from pg_stat_io
group by backend_type
