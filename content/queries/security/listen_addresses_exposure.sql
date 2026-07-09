with raw_setting as (
  select setting, source, pending_restart
  from pg_catalog.pg_settings
  where name = 'listen_addresses'
),
addresses as (
  select
    r.setting,
    r.source,
    r.pending_restart,
    btrim(value) as listen_address
  from raw_setting r
  cross join lateral regexp_split_to_table(r.setting, ',') as value
)
select
  'listen_addresses' as setting_name,
  setting as current_value,
  listen_address,
  source,
  pending_restart,
  case
    when listen_address in ('*', '0.0.0.0', '::') then 'high'
    else 'medium'
  end as risk_level,
  case
    when listen_address = '*' then 'PostgreSQL listens on all configured network interfaces'
    when listen_address in ('0.0.0.0', '::') then 'PostgreSQL listens on a wildcard network address'
    else 'PostgreSQL listens on a non-loopback address; verify this is intentional'
  end as risk_reason
from addresses
where listen_address not in ('', 'localhost', '127.0.0.1', '::1')
order by
  risk_level desc,
  listen_address asc
