select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  xact_commit::int8 as xact_commit,
  xact_rollback::int8 as xact_rollback,
  temp_bytes::int8 as temp_bytes,
  deadlocks::int8 as deadlocks
from pg_stat_database
where datname = current_database()
