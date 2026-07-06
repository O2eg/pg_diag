select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  tup_returned::int8 as tup_returned,
  tup_fetched::int8 as tup_fetched
from pg_stat_database
where datname = current_database()
