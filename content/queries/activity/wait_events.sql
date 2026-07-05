select
  coalesce(datname, 'server_process') as datname,
  coalesce(state, '') as state,
  coalesce(wait_event_type, 'CPU') as wait_event_type,
  coalesce(wait_event, 'CPU') as wait_event,
  query_id::text as query_id,
  count(*)::int8 as sessions
from pg_stat_activity
where state = 'active'
group by 1, 2, 3, 4, 5
order by sessions desc, wait_event_type asc, wait_event asc
