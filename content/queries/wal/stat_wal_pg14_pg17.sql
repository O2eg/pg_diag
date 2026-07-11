select
  wal_records,
  wal_fpi,
  wal_bytes::int8 as wal_bytes,
  wal_buffers_full,
  wal_write,
  wal_sync,
  wal_write_time,
  wal_sync_time,
  round(wal_bytes::numeric / nullif(wal_records, 0), 3) as bytes_per_record,
  current_setting('track_wal_io_timing')::boolean as track_wal_io_timing,
  stats_reset,
  extract(epoch from pg_catalog.clock_timestamp() - stats_reset)::int8 as stats_age_seconds
from pg_stat_wal
