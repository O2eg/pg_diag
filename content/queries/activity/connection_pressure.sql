with settings as (
  select
    current_setting('max_connections')::int as max_connections,
    current_setting('superuser_reserved_connections')::int as superuser_reserved_connections
),
activity as (
  select
    count(*)::int8 as used_connections,
    count(*) filter (where state = 'active')::int8 as active_connections,
    count(*) filter (where state = 'idle')::int8 as idle_connections,
    count(*) filter (where state = 'idle in transaction')::int8 as idle_in_transaction_connections,
    count(*) filter (where wait_event_type is not null)::int8 as waiting_connections
  from pg_stat_activity
)
select
  current_database() as datname,
  s.max_connections,
  s.superuser_reserved_connections,
  s.max_connections - s.superuser_reserved_connections as ordinary_connection_limit,
  a.used_connections,
  a.active_connections,
  a.idle_connections,
  a.idle_in_transaction_connections,
  a.waiting_connections,
  round(a.used_connections::numeric * 100 / nullif(s.max_connections, 0), 3) as used_pct,
  s.max_connections - a.used_connections as available_connections
from settings s
cross join activity a
