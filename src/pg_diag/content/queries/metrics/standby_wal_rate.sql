select
  statement_timestamp() as snapshot_time,
  'standby'::text as scope,
  pg_catalog.pg_wal_lsn_diff(pg_catalog.pg_last_wal_receive_lsn(), '0/0')::int8 as receive_bytes,
  pg_catalog.pg_wal_lsn_diff(pg_catalog.pg_last_wal_replay_lsn(), '0/0')::int8 as replay_bytes
where pg_catalog.pg_is_in_recovery()
