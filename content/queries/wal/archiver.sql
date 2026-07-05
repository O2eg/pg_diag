with current_wal as (
  select pg_walfile_name(pg_current_wal_lsn()) as current_wal_file
),
archiver as (
  select *
  from pg_stat_archiver
)
select
  archived_count,
  failed_count,
  last_archived_wal,
  last_archived_time,
  last_failed_wal,
  last_failed_time,
  case
    when last_archived_wal is null then null
    else greatest(
      0,
      (
        ('x' || substr(current_wal_file, 9, 8))::bit(32)::bigint
        -
        ('x' || substr(last_archived_wal, 9, 8))::bit(32)::bigint
      ) * 256
      +
      (
        ('x' || substr(current_wal_file, 17, 8))::bit(32)::bigint
        -
        ('x' || substr(last_archived_wal, 17, 8))::bit(32)::bigint
      )
    )
  end as pending_wal_count,
  stats_reset
from archiver
cross join current_wal
