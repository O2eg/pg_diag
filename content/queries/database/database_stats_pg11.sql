select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  numbackends,
  xact_commit,
  xact_rollback,
  blks_read,
  blks_hit,
  tup_returned,
  tup_fetched,
  tup_inserted,
  tup_updated,
  tup_deleted,
  conflicts,
  temp_files,
  temp_bytes,
  deadlocks,
  blk_read_time,
  blk_write_time,
  extract(epoch from (now() - pg_postmaster_start_time()))::int8 as postmaster_uptime_s,
  case when pg_is_in_recovery() then 1 else 0 end as in_recovery_int,
  system_identifier::text as sys_id,
  (select count(*) from pg_index i
    where not indisvalid
    and not exists ( /* leave out ones that are being actively rebuilt */
      select * from pg_locks l
      join pg_stat_activity a using (pid)
      where l.relation = i.indexrelid
      and a.state = 'active'
      and a.query ~* 'concurrently'
  )) as invalid_indexes
from
  pg_stat_database, pg_control_system()
where
  datname = current_database()
