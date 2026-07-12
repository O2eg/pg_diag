select
  statement_timestamp() as snapshot_time,
  'shared buffers'::text as scope,
  count(*) filter (where isdirty)::int8 as dirty_blocks,
  count(*) filter (where pinning_backends > 0)::int8 as pinned_blocks
from public.pg_buffercache;
