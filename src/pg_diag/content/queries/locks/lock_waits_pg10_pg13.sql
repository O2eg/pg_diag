with blocked_sessions as (
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
),
blocking_pairs as (
  select
    blocked.*,
    blockers.blocker_pid
  from blocked_sessions blocked
  cross join lateral (
    select distinct blocker_pid
    from unnest(blocked.blocker_pids) as blockers(blocker_pid)
  ) blockers
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
  left(regexp_replace(coalesce(pairs.query, ''), '\s+', ' ', 'g'), 1000) as blocked_query,
  case
    when pairs.query_start is null then null
    else greatest(
      (extract(epoch from clock_timestamp() - pairs.query_start) * 1000)::bigint,
      0
    )
  end as blocked_ms,
  pairs.blocker_pid::text as blocker_pid,
  blocker.usename::text as blocker_user,
  blocker.application_name::text as blocker_appname,
  blocker.state as blocker_state,
  blocker_lock.mode as blocker_mode,
  blocker_lock.granted as blocker_lock_granted,
  null::text as blocker_query_id,
  left(regexp_replace(coalesce(blocker.query, ''), '\s+', ' ', 'g'), 1000) as blocker_query,
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
  case
    when pairs.query_start is not null
      and clock_timestamp() - pairs.query_start >= interval '5 minutes' then 'high'
    when pairs.query_start is not null
      and clock_timestamp() - pairs.query_start >= interval '5 seconds' then 'medium'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when pairs.query_start is not null
      and clock_timestamp() - pairs.query_start >= interval '5 minutes'
      then 'A blocked query has run for at least five minutes'
    when pairs.query_start is not null
      and clock_timestamp() - pairs.query_start >= interval '5 seconds'
      then 'A blocked query has run for at least five seconds'
    else ''
  end as pg_diag_internal_reason
from blocking_pairs pairs
left join pg_stat_activity blocker on blocker.pid = pairs.blocker_pid
left join lateral (
  select lock_row.*
  from pg_locks lock_row
  where lock_row.pid = pairs.blocked_pid and not lock_row.granted
  order by lock_row.locktype, lock_row.mode
  limit 1
) waiting_lock on true
left join lateral (
  select lock_row.*
  from pg_locks lock_row
  where
    lock_row.pid = pairs.blocker_pid
    and lock_row.locktype is not distinct from waiting_lock.locktype
    and lock_row.database is not distinct from waiting_lock.database
    and lock_row.relation is not distinct from waiting_lock.relation
    and lock_row.page is not distinct from waiting_lock.page
    and lock_row.tuple is not distinct from waiting_lock.tuple
    and lock_row.virtualxid is not distinct from waiting_lock.virtualxid
    and lock_row.transactionid is not distinct from waiting_lock.transactionid
    and lock_row.classid is not distinct from waiting_lock.classid
    and lock_row.objid is not distinct from waiting_lock.objid
    and lock_row.objsubid is not distinct from waiting_lock.objsubid
  order by lock_row.granted desc, lock_row.locktype, lock_row.mode
  limit 1
) blocker_lock on true
left join lateral (
  select array_agg(distinct upstream_pid order by upstream_pid) as blocker_pids
  from unnest(
    case
      when pairs.blocker_pid > 0 then pg_blocking_pids(pairs.blocker_pid)
      else array[]::int[]
    end
  ) as blockers(upstream_pid)
) upstream on true
order by blocked_ms desc nulls last, pairs.blocked_pid, pairs.blocker_pid
limit 1000
