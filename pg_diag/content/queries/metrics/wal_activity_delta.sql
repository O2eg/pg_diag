select
  statement_timestamp() as snapshot_time,
  'cluster'::text as scope,
  stats_reset,
  wal_records::int8 as wal_records,
  wal_fpi::int8 as wal_fpi,
  wal_bytes::numeric as wal_bytes,
  wal_buffers_full::int8 as wal_buffers_full
from pg_catalog.pg_stat_wal
