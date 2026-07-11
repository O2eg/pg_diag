select
  statement_timestamp() as snapshot_time,
  pg_database.datname as datname,
  states.state,
  coalesce(activity.count, 0)::int8 as count
from (
  values
    ('active'),
    ('idle'),
    ('idle in transaction'),
    ('idle in transaction (aborted)'),
    ('fastpath function call'),
    ('disabled')
) as states(state)
cross join pg_database
left join (
  select
    datname,
    state,
    count(*)::int8 as count
  from pg_stat_activity
  group by datname, state
) as activity on activity.datname = pg_database.datname and activity.state = states.state
order by pg_database.datname, states.state
