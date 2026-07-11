select
  statement_timestamp() as snapshot_time,
  datid,
  datname,
  stats_reset,
  xact_commit::int8 as xact_commit,
  xact_rollback::int8 as xact_rollback,
  (xact_commit + xact_rollback)::int8 as total_xacts,
  blks_read::int8 as blks_read,
  blks_hit::int8 as blks_hit,
  (blks_read::numeric * current_setting('block_size')::int) as blks_read_bytes,
  tup_returned::int8 as tup_returned,
  tup_fetched::int8 as tup_fetched,
  tup_inserted::int8 as tup_inserted,
  tup_updated::int8 as tup_updated,
  tup_deleted::int8 as tup_deleted,
  temp_files::int8 as temp_files,
  temp_bytes::int8 as temp_bytes,
  deadlocks::int8 as deadlocks,
  round(blk_read_time::numeric, 3) as blk_read_time_ms,
  round(blk_write_time::numeric, 3) as blk_write_time_ms
from pg_stat_database
where datname is not null
