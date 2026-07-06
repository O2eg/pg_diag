select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  blk_read_time::float8 as blk_read_time,
  blk_write_time::float8 as blk_write_time
from pg_stat_database
where datname = current_database()
