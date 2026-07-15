select
  'data_checksums' as check_name,
  coalesce(setting, '<missing>') as current_value,
  'on' as expected_value,
  null::timestamptz as last_failure,
  'high' as risk_level,
  'data page checksums are disabled for this cluster' as risk_reason
from pg_catalog.pg_settings
where name = 'data_checksums'
  and lower(setting) <> 'on'
order by check_name asc
