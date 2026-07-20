select
  statement_timestamp() as snapshot_time,
  datname,
  tup_returned::int8 as tup_returned,
  tup_fetched::int8 as tup_fetched
from pg_stat_database
where datname is not null
