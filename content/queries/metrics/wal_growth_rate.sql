select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  wal_bytes::int8 as wal_bytes
from pg_stat_wal
