select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  tup_inserted::int8 as tup_inserted,
  tup_updated::int8 as tup_updated,
  tup_deleted::int8 as tup_deleted
from pg_stat_database
where datname = current_database()
