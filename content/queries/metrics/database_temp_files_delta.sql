select
  statement_timestamp() as snapshot_time,
  datname,
  temp_files::int8 as temp_files
from pg_stat_database
where datname is not null
