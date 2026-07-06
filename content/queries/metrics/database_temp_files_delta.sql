select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  temp_files::int8 as temp_files
from pg_stat_database
where datname = current_database()
