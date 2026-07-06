select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  temp_bytes::int8 as temp_bytes
from pg_stat_database
where datname = current_database()
