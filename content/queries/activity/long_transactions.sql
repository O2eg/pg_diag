select
  datname,
  usename,
  application_name,
  client_addr::text as client_addr,
  pid,
  state,
  wait_event_type,
  wait_event,
  backend_xid::text as backend_xid,
  backend_xmin::text as backend_xmin,
  case
    when backend_xid is null and backend_xmin is null then null
    else greatest(coalesce(age(backend_xid), 0), coalesce(age(backend_xmin), 0))::int8
  end as xid_age,
  extract(epoch from clock_timestamp() - state_change)::numeric(20, 3) as state_age_seconds,
  case
    when xact_start is null then null
    else extract(epoch from clock_timestamp() - xact_start)::numeric(20, 3)
  end as xact_age_seconds,
  case
    when query_start is null then null
    else extract(epoch from clock_timestamp() - query_start)::numeric(20, 3)
  end as query_age_seconds,
  query_id::text as query_id,
  left(regexp_replace(coalesce(query, ''), '\s+', ' ', 'g'), 500) as query,
  case
    when state in ('idle in transaction', 'idle in transaction (aborted)')
      and clock_timestamp() - xact_start >= interval '1 hour' then 'high'
    when clock_timestamp() - xact_start >= interval '1 day' then 'high'
    when state in ('idle in transaction', 'idle in transaction (aborted)') then 'medium'
    when clock_timestamp() - xact_start >= interval '15 minutes' then 'medium'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when state in ('idle in transaction', 'idle in transaction (aborted)')
      and clock_timestamp() - xact_start >= interval '1 hour'
      then 'A transaction has been idle for at least one hour'
    when clock_timestamp() - xact_start >= interval '1 day'
      then 'An active transaction has been open for at least one day'
    when state in ('idle in transaction', 'idle in transaction (aborted)')
      then 'A transaction has been idle for more than one minute'
    when clock_timestamp() - xact_start >= interval '15 minutes'
      then 'An active transaction has been open for at least 15 minutes'
    else ''
  end as pg_diag_internal_reason
from pg_stat_activity
where
  pid <> pg_backend_pid()
  and backend_type = 'client backend'
  and xact_start is not null
  and state in ('active', 'idle in transaction', 'idle in transaction (aborted)')
  and clock_timestamp() - xact_start > interval '1 minute'
order by xact_age_seconds desc nulls last, state_age_seconds desc
limit 100
