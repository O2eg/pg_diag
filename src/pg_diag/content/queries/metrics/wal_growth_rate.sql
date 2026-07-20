select
  statement_timestamp() as snapshot_time,
  'cluster'::text as scope,
  wal_bytes::int8 as wal_bytes
from pg_stat_wal
