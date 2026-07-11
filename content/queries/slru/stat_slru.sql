select
  name,
  blks_zeroed,
  blks_hit,
  blks_read,
  (blks_hit + blks_read)::int8 as block_accesses,
  round(100.0 * blks_hit / nullif(blks_hit + blks_read, 0), 2) as hit_pct,
  blks_written,
  blks_exists,
  flushes,
  truncates,
  stats_reset,
  extract(epoch from pg_catalog.clock_timestamp() - stats_reset)::int8 as stats_age_seconds
from pg_catalog.pg_stat_slru
order by blks_read desc, name asc
