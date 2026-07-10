with states(state) as (
  values
    ('active'),
    ('idle'),
    ('idle in transaction'),
    ('idle in transaction (aborted)'),
    ('fastpath function call'),
    ('disabled')
),
activity as (
  select
    coalesce(nullif(application_name, ''), '<unset>') as application_name,
    state,
    count(*)::int8 as sessions,
    max(extract(epoch from clock_timestamp() - xact_start))::numeric(20, 3)
      as max_tx_duration_seconds
  from pg_stat_activity
  where
    datname = current_database()
    and backend_type = 'client backend'
    and pid <> pg_backend_pid()
  group by 1, 2
)
select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  activity.application_name,
  states.state,
  coalesce(activity.sessions, 0)::int8 as count,
  activity.max_tx_duration_seconds as max_tx_duration
from states
left join activity on activity.state = states.state
order by count desc, states.state, activity.application_name nulls last
