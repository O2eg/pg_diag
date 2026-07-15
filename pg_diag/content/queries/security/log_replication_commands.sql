select
  name as setting_name,
  setting as current_value,
  source,
  pending_restart,
  'on' as expected_value,
  'medium' as risk_level,
  'replication commands are not logged' as risk_reason
from pg_catalog.pg_settings
where name = 'log_replication_commands'
  and setting <> 'on'
order by setting_name asc
