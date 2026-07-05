select
  name,
  blks_zeroed,
  blks_hit,
  blks_read,
  blks_written,
  blks_exists,
  flushes,
  truncates,
  stats_reset
from pg_stat_slru
order by blks_read desc, name asc
