with settings as (
  select
    current_setting('max_connections')::int as max_connections,
    coalesce(current_setting('reserved_connections', true), '0')::int as reserved_connections,
    current_setting('superuser_reserved_connections')::int as superuser_reserved_connections
),
activity as (
  select
    count(*)::int8 as used_connections,
    count(*) filter (where state = 'active')::int8 as active_connections,
    count(*) filter (where state = 'idle')::int8 as idle_connections,
    count(*) filter (
      where state in ('idle in transaction', 'idle in transaction (aborted)')
    )::int8 as idle_in_transaction_connections,
    count(*) filter (
      where state = 'active' and wait_event_type is not null
    )::int8 as waiting_connections
  from pg_stat_activity
  where backend_type = 'client backend'
),
pressure as (
  select
    s.*,
    a.*,
    s.max_connections - s.reserved_connections - s.superuser_reserved_connections
      as ordinary_connection_limit,
    greatest(
      s.max_connections - s.reserved_connections - s.superuser_reserved_connections
        - a.used_connections,
      0
    ) as ordinary_available_connections,
    greatest(
      s.max_connections - s.superuser_reserved_connections - a.used_connections,
      0
    ) as reserved_role_available_connections,
    greatest(s.max_connections - a.used_connections, 0) as total_available_connections
  from settings s
  cross join activity a
)
select
  'cluster'::text as scope,
  current_database() as connected_database,
  max_connections,
  reserved_connections,
  superuser_reserved_connections,
  ordinary_connection_limit,
  max_connections - superuser_reserved_connections as reserved_role_connection_limit,
  used_connections,
  active_connections,
  idle_connections,
  idle_in_transaction_connections,
  waiting_connections,
  (used_connections::numeric * 100 / nullif(max_connections, 0)) as used_pct,
  ordinary_available_connections,
  reserved_role_available_connections,
  total_available_connections,
  case
    when total_available_connections <= 1 then 'high'
    when ordinary_available_connections <= greatest(2, ceil(ordinary_connection_limit * 0.05)::int)
      then 'medium'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when total_available_connections <= 1
      then 'At most one total client connection slot remains'
    when ordinary_available_connections <= greatest(2, ceil(ordinary_connection_limit * 0.05)::int)
      then 'Ordinary client connection headroom is at or below 5% (minimum threshold: two slots)'
    else ''
  end as pg_diag_internal_reason
from pressure
