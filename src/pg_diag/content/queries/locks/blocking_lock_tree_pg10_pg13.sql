with waiters_bounded as (
  select a.pid, pg_blocking_pids(a.pid) as blocker_pids
  from pg_stat_activity a
  where a.datname = current_database()
    and a.pid <> pg_backend_pid()
    and a.backend_type = 'client backend'
    and a.state = 'active'
    and a.wait_event_type = 'Lock'
  order by a.pid
  limit 1501
),
waiter_coverage as (
  select (count(*) > 1500) as waiter_sample_truncated from waiters_bounded
),
waiters as (
  select w.pid, w.blocker_pids, (cardinality(w.blocker_pids) > 50) as blockers_truncated
  from waiters_bounded w
  order by w.pid
  limit 1500
),
blocker_coverage as (
  select coalesce(bool_or(w.blockers_truncated), false) as any_blockers_truncated from waiters w
),
edges as (
  select b.blocker_pid, w.pid as blocked_pid, w.blockers_truncated
  from waiters w
  cross join lateral (
    select distinct blocker_pid
    from unnest(w.blocker_pids[1:50]) as u(blocker_pid)
  ) b
  where b.blocker_pid > 0
),
roots as (
  select distinct e.blocker_pid as pid
  from edges e
  where not exists (
    select 1 from edges inner_edge where inner_edge.blocked_pid = e.blocker_pid
  )
),
tree_bounded as (
  with recursive tree(root_pid, pid, blocked_by_pid, depth, path, blockers_truncated) as (
    select r.pid, r.pid, null::int, 0, array[r.pid], false
    from roots r

    union all

    select t.root_pid, e.blocked_pid, e.blocker_pid, t.depth + 1, t.path || e.blocked_pid,
           e.blockers_truncated
    from tree t
    join edges e on e.blocker_pid = t.pid
    where not e.blocked_pid = any(t.path)
      and t.depth < 32
  )
  select * from tree limit 5001
),
tree_coverage as (
  select (count(*) > 5000) as tree_truncated from tree_bounded
),
tree_sample as (
  select * from tree_bounded limit 5000
),
root_totals as (
  select t.root_pid, (count(distinct t.pid) - 1)::int8 as blocked_sessions
  from tree_sample t
  group by t.root_pid
),
numbered as (
  select
    t.*,
    rt.blocked_sessions as root_blocked_sessions,
    row_number() over (order by rt.blocked_sessions desc, t.root_pid, t.path) as tree_order
  from tree_sample t
  join root_totals rt on rt.root_pid = t.root_pid
)
select
  n.tree_order::int8 as tree_order,
  n.root_pid::text as root_pid,
  n.depth::int8 as depth,
  n.pid::text as pid,
  n.blocked_by_pid::text as blocked_by_pid,
  (
    select string_agg(u.step_pid::text, ' -> ' order by u.ord)
    from unnest(n.path) with ordinality u(step_pid, ord)
  ) as path,
  n.root_blocked_sessions,
  (n.depth = 0) as is_root,
  a.usename::text as user_name,
  a.application_name::text as application_name,
  a.state,
  concat_ws(': ', a.wait_event_type, a.wait_event) as wait_event,
  null::text as query_id,
  left(coalesce(a.query, ''), 8000) as query,
  case
    when a.xact_start is null then null
    else greatest((extract(epoch from clock_timestamp() - a.xact_start) * 1000)::bigint, 0)
  end as transaction_ms,
  case
    when a.query_start is null then null
    else greatest((extract(epoch from clock_timestamp() - a.query_start) * 1000)::bigint, 0)
  end as query_ms,
  n.blockers_truncated,
  waiter_coverage.waiter_sample_truncated,
  tree_coverage.tree_truncated,
  case
    when n.depth = 0 and n.root_blocked_sessions >= 10 then 'high'
    when n.depth >= 2 then 'medium'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when n.depth = 0 and n.root_blocked_sessions >= 10
      then 'This root session directly or transitively blocks 10 or more sessions'
    when n.depth >= 2
      then 'This session waits behind a lock cascade at least two levels deep'
    else ''
  end as pg_diag_internal_reason
from numbered n
cross join waiter_coverage
cross join tree_coverage
left join pg_stat_activity a on a.pid = n.pid

union all

select
  null::int8 as tree_order,
  '[coverage]'::text as root_pid,
  null::int8 as depth,
  '[coverage]'::text as pid,
  null::text as blocked_by_pid,
  null::text as path,
  null::int8 as root_blocked_sessions,
  false as is_root,
  null::text as user_name,
  null::text as application_name,
  null::text as state,
  null::text as wait_event,
  null::text as query_id,
  null::text as query,
  null::bigint as transaction_ms,
  null::bigint as query_ms,
  blocker_coverage.any_blockers_truncated as blockers_truncated,
  waiter_coverage.waiter_sample_truncated,
  tree_coverage.tree_truncated,
  'unknown'::text as pg_diag_internal_severity,
  concat_ws(
    '; ',
    case when waiter_coverage.waiter_sample_truncated
      then 'More than 1500 sessions wait on locks; findings above are proven but the tree is built from a partial sample' end,
    case when tree_coverage.tree_truncated
      then 'The blocking tree exceeded 5000 nodes; branches above are proven but the tree is incomplete' end,
    case when blocker_coverage.any_blockers_truncated
      then 'Some sessions have more than 50 blockers; only the first 50 per session were followed' end
  ) as pg_diag_internal_reason
from waiter_coverage
cross join tree_coverage
cross join blocker_coverage
where waiter_coverage.waiter_sample_truncated
  or tree_coverage.tree_truncated
  or blocker_coverage.any_blockers_truncated

order by tree_order nulls last
limit 5001
