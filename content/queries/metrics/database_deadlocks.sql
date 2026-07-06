select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  deadlocks::int8 as deadlocks
from pg_stat_database
where datname = current_database()
