select
  statement_timestamp() as snapshot_time,
  'shared buffers'::text as scope,
  count(*) filter (where relfilenode is not null)::int8 as used_blocks,
  count(*) filter (where relfilenode is null)::int8 as unused_blocks
from public.pg_buffercache;
