select /* pgwatch_generated */
  current_database() as datname,
  buffers_clean,
  maxwritten_clean,
  buffers_alloc,
  (extract(epoch from now() - stats_reset))::int as last_reset_s
from
  pg_stat_bgwriter
