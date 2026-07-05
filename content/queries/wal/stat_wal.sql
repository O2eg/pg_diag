select
  wal_records,
  wal_fpi,
  wal_bytes::int8 as wal_bytes,
  wal_buffers_full,
  round(wal_bytes::numeric / nullif(wal_records, 0), 3) as bytes_per_record,
  stats_reset
from pg_stat_wal
