select
  statement_timestamp() as snapshot_time,
  'standby'::text as scope,
  extract(
    epoch from pg_catalog.clock_timestamp() - pg_catalog.pg_last_xact_replay_timestamp()
  )::float8 as replay_delay_seconds
where pg_catalog.pg_is_in_recovery()
