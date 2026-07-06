select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  blks_read::int8 as blks_read,
  blks_hit::int8 as blks_hit
from pg_stat_database
where datname = current_database()
