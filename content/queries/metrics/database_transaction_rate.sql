select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  xact_commit::int8 as xact_commit,
  xact_rollback::int8 as xact_rollback
from pg_stat_database
where datname = current_database()
