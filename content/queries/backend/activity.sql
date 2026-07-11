select
  pid,
  leader_pid,
  coalesce(backend_type, '') as backend_type,
  coalesce(datname, '') as datname,
  coalesce(usename, '') as usename,
  coalesce(application_name, '') as application_name,
  client_addr::text as client_addr,
  coalesce(state, '') as state,
  case
    when wait_event_type is not null then wait_event_type
    when state = 'active' then 'CPU'
    else ''
  end as wait_event_type,
  case
    when wait_event is not null then wait_event
    when state = 'active' then 'CPU'
    else ''
  end as wait_event,
  query_id::text as query_id,
  backend_start,
  state_change,
  query_start,
  xact_start,
  case
    when state = 'active' then extract(epoch from statement_timestamp() - query_start)::int8
    else null
  end as query_age_seconds,
  extract(epoch from now() - xact_start)::int8 as xact_age_seconds,
  left(coalesce(query, ''), 1000) as query
from pg_stat_activity
where pid <> pg_backend_pid()
order by
  coalesce(state = 'active', false) desc,
  query_age_seconds desc nulls last,
  xact_age_seconds desc nulls last,
  pid
limit 200
