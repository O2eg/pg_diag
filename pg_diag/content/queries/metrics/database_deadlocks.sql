select
  statement_timestamp() as snapshot_time,
  datname,
  deadlocks::int8 as deadlocks
from pg_stat_database
where datname is not null
