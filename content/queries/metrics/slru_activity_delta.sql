select
  statement_timestamp() as snapshot_time,
  name,
  stats_reset,
  blks_zeroed::int8 as blks_zeroed,
  blks_hit::int8 as blks_hit,
  blks_read::int8 as blks_read,
  blks_written::int8 as blks_written,
  blks_exists::int8 as blks_exists,
  flushes::int8 as flushes,
  truncates::int8 as truncates
from pg_catalog.pg_stat_slru
order by blks_read desc nulls last, name
