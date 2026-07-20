select
  datname,
  usename,
  application_name,
  client_addr::text as client_addr,
  pid,
  wait_event_type,
  wait_event,
  extract(epoch from clock_timestamp() - state_change)::numeric as idle_seconds,
  case
    when xact_start is null then null
    else extract(epoch from clock_timestamp() - xact_start)::numeric
  end as xact_age_seconds,
  backend_xid::text as backend_xid,
  backend_xmin::text as backend_xmin,
  case
    when backend_xid is null and backend_xmin is null then null
    else greatest(coalesce(age(backend_xid), 0), coalesce(age(backend_xmin), 0))::int8
  end as xid_age,
  left(regexp_replace(coalesce(query, ''), '\s+', ' ', 'g'), 500) as query,
  case
    when clock_timestamp() - state_change >= interval '1 hour' then 'high'
    else 'medium'
  end as pg_diag_internal_severity,
  case
    when clock_timestamp() - state_change >= interval '1 hour'
      then 'A session has been idle in an open transaction for at least one hour'
    else 'A session has been idle in an open transaction for more than one minute'
  end as pg_diag_internal_reason
from pg_stat_activity
where
  pid <> pg_backend_pid()
  and backend_type = 'client backend'
  and state in ('idle in transaction', 'idle in transaction (aborted)')
  and clock_timestamp() - state_change > interval '1 minute'
order by idle_seconds desc
limit 100
