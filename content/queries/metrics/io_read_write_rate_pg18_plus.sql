select
  statement_timestamp() as snapshot_time,
  'cluster'::text as scope,
  backend_type,
  sum(coalesce(read_bytes, 0))::int8 as read_bytes,
  sum(coalesce(write_bytes, 0))::int8 as write_bytes
from pg_stat_io
group by backend_type
