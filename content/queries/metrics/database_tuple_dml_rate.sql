select
  statement_timestamp() as snapshot_time,
  datname,
  tup_inserted::int8 as tup_inserted,
  tup_updated::int8 as tup_updated,
  tup_deleted::int8 as tup_deleted
from pg_stat_database
where datname is not null
