select
  statement_timestamp() as snapshot_time,
  'shared buffers'::text as scope,
  summary.buffers_used::int8 as used_blocks,
  summary.buffers_unused::int8 as unused_blocks
from public.pg_buffercache_summary() summary;
