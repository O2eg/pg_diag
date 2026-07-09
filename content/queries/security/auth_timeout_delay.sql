with settings as (
  select
    max(setting) filter (where name = 'authentication_timeout') as authentication_timeout,
    max(unit) filter (where name = 'authentication_timeout') as authentication_timeout_unit,
    max(setting) filter (where name = 'shared_preload_libraries') as shared_preload_libraries,
    max(setting) filter (where name = 'auth_delay.milliseconds') as auth_delay_milliseconds,
    max(setting) filter (where name = 'auth_delay.failure_timeout') as auth_delay_failure_timeout,
    max(unit) filter (where name = 'auth_delay.failure_timeout') as auth_delay_failure_timeout_unit
  from pg_catalog.pg_settings
  where name in (
    'authentication_timeout',
    'shared_preload_libraries',
    'auth_delay.milliseconds',
    'auth_delay.failure_timeout'
  )
),
evaluated as (
  select
    authentication_timeout,
    authentication_timeout_unit,
    shared_preload_libraries,
    auth_delay_milliseconds,
    auth_delay_failure_timeout,
    auth_delay_failure_timeout_unit,
    case
      when coalesce(authentication_timeout ~ '^[0-9]+$', false) then authentication_timeout::numeric
      else null
    end as authentication_timeout_numeric,
    case
      when coalesce(auth_delay_milliseconds ~ '^[0-9]+$', false) then auth_delay_milliseconds::numeric
      else null
    end as auth_delay_milliseconds_numeric,
    case
      when coalesce(auth_delay_failure_timeout ~ '^[0-9]+$', false) then auth_delay_failure_timeout::numeric
      else null
    end as auth_delay_failure_timeout_numeric,
    lower(coalesce(shared_preload_libraries, '')) like '%auth_delay%' as auth_delay_preloaded
  from settings
)
select
  'authentication_timeout' as check_name,
  concat(authentication_timeout, coalesce(authentication_timeout_unit, '')) as current_value,
  'positive value, normally 60s or less' as expected_value,
  case
    when authentication_timeout_numeric <= 0 then 'high'
    else 'medium'
  end as risk_level,
  case
    when authentication_timeout_numeric <= 0 then 'authentication_timeout is disabled'
    else 'authentication_timeout is higher than the expected audit posture'
  end as risk_reason
from evaluated
where authentication_timeout_numeric is null
  or authentication_timeout_numeric <= 0
  or authentication_timeout_numeric > 60

union all

select
  'failed_authentication_delay' as check_name,
  case
    when auth_delay_failure_timeout is not null then
      concat('auth_delay.failure_timeout=', auth_delay_failure_timeout, coalesce(auth_delay_failure_timeout_unit, ''))
    when auth_delay_milliseconds is not null then concat('auth_delay.milliseconds=', auth_delay_milliseconds)
    when shared_preload_libraries is not null then concat('shared_preload_libraries=', shared_preload_libraries)
    else '<unset>'
  end as current_value,
  'auth_delay or PostgreSQL failed-auth delay configured with a positive value' as expected_value,
  'medium' as risk_level,
  'failed authentication responses have no configured delay' as risk_reason
from evaluated
where not (
  coalesce(auth_delay_failure_timeout_numeric > 0, false)
  or (auth_delay_preloaded and coalesce(auth_delay_milliseconds_numeric > 0, false))
)
order by check_name asc
