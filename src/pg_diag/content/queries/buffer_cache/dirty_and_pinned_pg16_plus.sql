select
  statement_timestamp() as snapshot_time,
  'shared buffers'::text as scope,
  summary.buffers_dirty::int8 as dirty_blocks,
  summary.buffers_pinned::int8 as pinned_blocks
from public.pg_buffercache_summary() summary;
