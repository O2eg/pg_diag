with sa_snapshot as (
  select *
  from pg_stat_activity
  where
    datname = current_database()
    and pid <> pg_backend_pid()
    and state in ('active', 'idle in transaction', 'idle in transaction (aborted)')
),
pid_tables as (
  select distinct on (pid) pid, relation::regclass::text as table_name
  from pg_catalog.pg_locks
  where relation is not null
    and locktype in ('tuple', 'relation')
    and relation::regclass::text not like '%_pkey'
    and relation::regclass::text not like '%_idx'
  order by pid, locktype
)
select
  blocked.pid::text as blocked_pid,
  current_database() as datname,
  blocked_stm.usename::text as blocked_user,
  blocked_stm.application_name::text as blocked_appname,
  blocked.mode as blocked_mode,
  blocked.locktype as blocked_locktype,
  coalesce(blocked.relation::regclass::text, blocked_tbl.table_name, '') as blocked_table,
  blocked_stm.query_id::text as blocked_query_id,
  left(regexp_replace(coalesce(blocked_stm.query, ''), '\s+', ' ', 'g'), 1000) as blocked_query,
  (extract(epoch from (clock_timestamp() - blocked_stm.state_change)) * 1000)::bigint as blocked_ms,
  blocker.pid::text as blocker_pid,
  blocker_stm.usename::text as blocker_user,
  blocker_stm.application_name::text as blocker_appname,
  blocker.mode as blocker_mode,
  blocker.locktype as blocker_locktype,
  coalesce(blocker.relation::regclass::text, blocker_tbl.table_name, '') as blocker_table,
  blocker_stm.query_id::text as blocker_query_id,
  left(regexp_replace(coalesce(blocker_stm.query, ''), '\s+', ' ', 'g'), 1000) as blocker_query,
  (extract(epoch from (clock_timestamp() - blocker_stm.xact_start)) * 1000)::bigint as blocker_tx_ms
from pg_catalog.pg_locks as blocked
join sa_snapshot as blocked_stm on blocked_stm.pid = blocked.pid
join pg_catalog.pg_locks as blocker on
  blocked.pid <> blocker.pid
  and blocker.granted
  and (
    (blocked.database = blocker.database)
    or (blocked.database is null and blocker.database is null)
  )
  and (
    blocked.relation = blocker.relation
    or blocked.transactionid = blocker.transactionid
  )
join sa_snapshot as blocker_stm on blocker_stm.pid = blocker.pid
left join pid_tables as blocked_tbl on blocked_tbl.pid = blocked.pid
left join pid_tables as blocker_tbl on blocker_tbl.pid = blocker.pid
where not blocked.granted
order by blocked_ms desc
limit 10000
