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
    datname,
    coalesce(nullif(application_name, ''), '<unset>') as application_name,
    state,
    count(*)::int8 as sessions,
    max(extract(epoch from clock_timestamp() - xact_start))::numeric
      as max_tx_duration_seconds
  from pg_stat_activity
  where
    datname is not null
    and backend_type = 'client backend'
    and pid <> pg_backend_pid()
  group by 1, 2, 3
),
databases as (
  select datname
  from pg_database
)
select
  statement_timestamp() as snapshot_time,
  databases.datname,
  activity.application_name,
  states.state,
  coalesce(activity.sessions, 0)::int8 as count,
  activity.max_tx_duration_seconds as max_tx_duration
from databases
cross join states
left join activity
  on activity.datname = databases.datname
  and activity.state = states.state
order by count desc, databases.datname, states.state, activity.application_name nulls last
