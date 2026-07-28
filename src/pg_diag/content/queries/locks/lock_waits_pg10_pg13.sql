with blocked_sessions_bounded as (
  select
    activity.pid as blocked_pid,
    activity.datname,
    activity.usename,
    activity.application_name,
    activity.state,
    activity.query_start,
    activity.query,
    pg_blocking_pids(activity.pid) as blocker_pids
  from pg_stat_activity activity
  where
    activity.datname = current_database()
    and activity.pid <> pg_backend_pid()
    and activity.backend_type = 'client backend'
    and activity.state = 'active'
    and activity.wait_event_type = 'Lock'
  order by activity.pid
  limit 3001
),
blocked_session_coverage as (
  select (count(*) > 3000) as blocked_sessions_truncated
  from blocked_sessions_bounded
),
blocked_sessions as (
  select
    bounded.*,
    (cardinality(bounded.blocker_pids) > 50) as direct_blockers_truncated
  from blocked_sessions_bounded bounded
  order by bounded.blocked_pid
  limit 3000
),
blocking_pairs_bounded as (
  select
    blocked.*,
    blockers.blocker_pid
  from blocked_sessions blocked
  cross join lateral (
    select distinct blocker_pid
    from unnest(blocked.blocker_pids[1:50]) as blockers(blocker_pid)
  ) blockers
  limit 3001
),
blocking_pair_coverage as (
  select (count(*) > 3000) as blocking_pairs_truncated
  from blocking_pairs_bounded
),
blocking_pairs as (
  select *
  from blocking_pairs_bounded
  limit 3000
),
selected_pair_coverage as (
  select
    count(*)::int8 as selected_pair_count,
    (count(*) > 1000) as result_truncated
  from blocking_pairs
),
relevant_pids as (
  select blocked_pid as pid
  from blocking_pairs
  union
  select blocker_pid
  from blocking_pairs
  where blocker_pid > 0
),
lock_snapshot as (
  select lock_row.*
  from pg_locks lock_row
  join relevant_pids relevant on relevant.pid = lock_row.pid
),
waiting_locks as (
  select distinct on (lock_row.pid)
    lock_row.*
  from lock_snapshot lock_row
  where not lock_row.granted
  order by lock_row.pid, lock_row.locktype, lock_row.mode
),
representative_locks as (
  select distinct on (
    lock_row.pid,
    lock_row.locktype,
    lock_row.database,
    lock_row.relation,
    lock_row.page,
    lock_row.tuple,
    lock_row.virtualxid,
    lock_row.transactionid::text,
    lock_row.classid,
    lock_row.objid,
    lock_row.objsubid
  )
    lock_row.*
  from lock_snapshot lock_row
  order by
    lock_row.pid,
    lock_row.locktype,
    lock_row.database nulls first,
    lock_row.relation nulls first,
    lock_row.page nulls first,
    lock_row.tuple nulls first,
    lock_row.virtualxid nulls first,
    lock_row.transactionid::text nulls first,
    lock_row.classid nulls first,
    lock_row.objid nulls first,
    lock_row.objsubid nulls first,
    lock_row.granted desc,
    lock_row.mode
)
select
  pairs.blocked_pid::text as blocked_pid,
  pairs.datname,
  pairs.usename::text as blocked_user,
  pairs.application_name::text as blocked_appname,
  pairs.state as blocked_state,
  waiting_lock.mode as blocked_mode,
  waiting_lock.locktype as blocked_locktype,
  case
    when waiting_lock.relation is not null then concat_ws(
      ':',
      waiting_lock.relation::regclass::text,
      case when waiting_lock.page is not null then 'page=' || waiting_lock.page::text end,
      case when waiting_lock.tuple is not null then 'tuple=' || waiting_lock.tuple::text end
    )
    when waiting_lock.transactionid is not null then 'transactionid:' || waiting_lock.transactionid::text
    when waiting_lock.virtualxid is not null then 'virtualxid:' || waiting_lock.virtualxid
    when waiting_lock.locktype = 'advisory' then format(
      'advisory:%s:%s:%s', waiting_lock.classid, waiting_lock.objid, waiting_lock.objsubid
    )
    else concat_ws(':', waiting_lock.locktype, waiting_lock.database, waiting_lock.classid, waiting_lock.objid)
  end as blocked_target,
  null::text as blocked_query_id,
  left(coalesce(pairs.query, ''), 8000) as blocked_query,
  case
    when pairs.query_start is null then null
    else greatest(
      (extract(epoch from clock_timestamp() - pairs.query_start) * 1000)::bigint,
      0
    )
  end as blocked_ms,
  'pg_stat_activity.query_start_upper_bound'::text as blocked_duration_source,
  pairs.blocker_pid::text as blocker_pid,
  blocker.usename::text as blocker_user,
  blocker.application_name::text as blocker_appname,
  blocker.state as blocker_state,
  blocker_lock.mode as blocker_mode,
  blocker_lock.granted as blocker_lock_granted,
  null::text as blocker_query_id,
  left(coalesce(blocker.query, ''), 8000) as blocker_query,
  case
    when blocker.xact_start is null then null
    else greatest(
      (extract(epoch from clock_timestamp() - blocker.xact_start) * 1000)::bigint,
      0
    )
  end as blocker_tx_ms,
  case
    when pairs.blocker_pid = 0 then true
    else coalesce(cardinality(upstream.blocker_pids), 0) = 0
  end as blocker_is_root,
  case
    when pairs.blocker_pid = 0 then null
    else array_to_string(upstream.blocker_pids, ',')
  end as blocker_blocked_by_pids,
  pairs.direct_blockers_truncated,
  blocked_coverage.blocked_sessions_truncated,
  pair_coverage.blocking_pairs_truncated,
  result_coverage.selected_pair_count,
  result_coverage.result_truncated,
  (cardinality(upstream_all.blocker_pids) > 50) as upstream_blockers_truncated,
  'unknown'::text as pg_diag_internal_severity,
  'PostgreSQL 10-13 does not expose pg_locks.waitstart; blocked_ms is the query age and only an upper bound for lock-wait duration'::text as pg_diag_internal_reason
from blocking_pairs pairs
cross join blocked_session_coverage blocked_coverage
cross join blocking_pair_coverage pair_coverage
cross join selected_pair_coverage result_coverage
left join pg_stat_activity blocker on blocker.pid = pairs.blocker_pid
left join waiting_locks waiting_lock on waiting_lock.pid = pairs.blocked_pid
left join representative_locks blocker_lock
  on blocker_lock.pid = pairs.blocker_pid
    and blocker_lock.locktype is not distinct from waiting_lock.locktype
    and blocker_lock.database is not distinct from waiting_lock.database
    and blocker_lock.relation is not distinct from waiting_lock.relation
    and blocker_lock.page is not distinct from waiting_lock.page
    and blocker_lock.tuple is not distinct from waiting_lock.tuple
    and blocker_lock.virtualxid is not distinct from waiting_lock.virtualxid
    and blocker_lock.transactionid is not distinct from waiting_lock.transactionid
    and blocker_lock.classid is not distinct from waiting_lock.classid
    and blocker_lock.objid is not distinct from waiting_lock.objid
    and blocker_lock.objsubid is not distinct from waiting_lock.objsubid
left join lateral (
  select
    case
      when pairs.blocker_pid > 0 then pg_blocking_pids(pairs.blocker_pid)
      else array[]::int[]
    end as blocker_pids
) upstream_all on true
left join lateral (
  select array_agg(distinct upstream_pid order by upstream_pid) as blocker_pids
  from unnest(upstream_all.blocker_pids[1:50]) as blockers(upstream_pid)
) upstream on true
order by blocked_ms desc nulls last, pairs.blocked_pid, pairs.blocker_pid
limit 1000
