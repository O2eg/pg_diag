select
  statement_timestamp() as snapshot_time,
  'cluster'::text as scope,
  backend_type,
  sum(read_bytes)::int8 as read_bytes,
  sum(write_bytes)::int8 as write_bytes
from pg_stat_io
group by backend_type
