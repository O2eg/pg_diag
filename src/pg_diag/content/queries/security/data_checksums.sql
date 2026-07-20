with checksum_setting as (
  select setting
  from pg_catalog.pg_settings
  where name = 'data_checksums'
),
checksum_failures as (
  select
    count(*) filter (where checksum_failures > 0)::int8 as database_count_with_failures,
    coalesce(sum(checksum_failures), 0)::int8 as checksum_failures_total,
    max(checksum_last_failure) as checksum_last_failure
  from pg_catalog.pg_stat_database
)
select
  'data_checksums' as check_name,
  coalesce(cs.setting, '<missing>') as current_value,
  'on' as expected_value,
  null::timestamptz as last_failure,
  'high' as risk_level,
  'data page checksums are disabled for this cluster' as risk_reason
from checksum_setting cs
where lower(cs.setting) <> 'on'

union all

select
  'checksum_failures' as check_name,
  cf.checksum_failures_total::text as current_value,
  '0' as expected_value,
  cf.checksum_last_failure as last_failure,
  'high' as risk_level,
  'checksum failures have been reported in pg_stat_database' as risk_reason
from checksum_failures cf
where cf.checksum_failures_total > 0
order by check_name asc
