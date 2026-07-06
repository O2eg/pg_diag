select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  numbackends::int8 as numbackends
from pg_stat_database
where datname = current_database()
