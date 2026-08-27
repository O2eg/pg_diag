select
  statement_timestamp() as snapshot_time,
  'standby'::text as scope,
  pg_catalog.pg_wal_lsn_diff(
    pg_catalog.pg_last_wal_receive_lsn(),
    pg_catalog.pg_last_wal_replay_lsn()
  )::int8 as receive_replay_lag_bytes
where pg_catalog.pg_is_in_recovery()
