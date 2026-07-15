select
  statement_timestamp() as snapshot_time,
  'cluster'::text as scope,
  stats_reset,
  archived_count::int8 as archived_count,
  failed_count::int8 as failed_count,
  last_archived_wal,
  last_failed_wal
from pg_catalog.pg_stat_archiver
