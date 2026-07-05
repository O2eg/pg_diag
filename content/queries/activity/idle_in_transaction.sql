select
  datname,
  usename,
  application_name,
  client_addr::text as client_addr,
  pid,
  wait_event_type,
  wait_event,
  extract(epoch from clock_timestamp() - state_change)::numeric(20, 3) as idle_seconds,
  case
    when xact_start is null then null
    else extract(epoch from clock_timestamp() - xact_start)::numeric(20, 3)
  end as xact_age_seconds,
  backend_xid::text as backend_xid,
  backend_xmin::text as backend_xmin,
  greatest(coalesce(age(backend_xid), 0), coalesce(age(backend_xmin), 0))::int8 as xid_age,
  left(regexp_replace(coalesce(query, ''), '\s+', ' ', 'g'), 500) as query
from pg_stat_activity
where
  pid <> pg_backend_pid()
  and state = 'idle in transaction'
  and clock_timestamp() - state_change > interval '1 minute'
order by idle_seconds desc
limit 100
