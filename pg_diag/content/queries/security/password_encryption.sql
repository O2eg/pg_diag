select
  name as setting_name,
  setting as current_value,
  source,
  pending_restart,
  'scram-sha-256' as expected_value,
  case
    when lower(setting) = 'md5' then 'high'
    else 'medium'
  end as risk_level,
  'password_encryption is not set to scram-sha-256' as risk_reason
from pg_catalog.pg_settings
where name = 'password_encryption'
  and lower(setting) <> 'scram-sha-256'
order by setting_name asc
