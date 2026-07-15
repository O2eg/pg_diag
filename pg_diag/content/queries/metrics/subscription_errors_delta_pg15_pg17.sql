select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  subid,
  subname,
  stats_reset,
  apply_error_count::int8 as apply_error_count,
  sync_error_count::int8 as sync_error_count,
  null::int8 as conflict_count
from pg_catalog.pg_stat_subscription_stats
order by (apply_error_count + sync_error_count) desc nulls last, subname
limit 50
