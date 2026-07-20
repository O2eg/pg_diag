select
  statement_timestamp() as snapshot_time,
  datname,
  numbackends::int8 as numbackends
from pg_stat_database
where datname is not null
