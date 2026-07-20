select
  coalesce(datname, 'server_process') as datname,
  coalesce(nullif(application_name, ''), '<unset>') as application_name,
  coalesce(wait_event_type, 'Not waiting') as wait_event_type,
  coalesce(wait_event, 'Active without wait event') as wait_event,
  null::text as query_id,
  left(regexp_replace(coalesce(a.query, ''), '\s+', ' ', 'g'), 1000) as query,
  count(*)::int8 as sessions
from pg_stat_activity a
where
  a.state = 'active'
  and a.pid <> pg_backend_pid()
group by 1, 2, 3, 4, 5, 6
order by sessions desc, wait_event_type asc, wait_event asc
limit 100
