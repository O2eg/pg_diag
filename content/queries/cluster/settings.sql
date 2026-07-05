with base as (
  select
    name,
    -- Use reset_val for lock_timeout/statement_timeout because the collector session can override them
    -- during collection.
    case
      when name in ('lock_timeout', 'statement_timeout') then reset_val
      else setting
    end as effective_setting,
    unit,
    category,
    vartype,
    -- For lock_timeout/statement_timeout, compare reset_val with boot_val
    -- since source becomes 'session' during collection.
    case
      when name in ('lock_timeout', 'statement_timeout') then (reset_val = boot_val)
      else (source = 'default')
    end as is_default_bool
  from pg_settings
), with_numeric as (
  select
    *,
    case
      when effective_setting ~ '^-?[0-9]+(\.[0-9]+)?$' then effective_setting::numeric
      else null
    end as numeric_value
  from base
)
select
  name as setting_name,
  effective_setting as setting_value,
  case
    when numeric_value is null then null
    when numeric_value < 0 then effective_setting
    when unit = '8kB' then pg_size_pretty((numeric_value * 8192)::bigint)
    when unit = 'kB' then pg_size_pretty((numeric_value * 1024)::bigint)
    when unit = 'MB' then pg_size_pretty((numeric_value * 1024 * 1024)::bigint)
    when unit = 'GB' then pg_size_pretty((numeric_value * 1024 * 1024 * 1024)::bigint)
    when unit = 'B' then pg_size_pretty(numeric_value::bigint)
    when unit = 'ms' then
      case
        when numeric_value = 0 then '0 ms'
        when numeric_value < 1000 then numeric_value::text || ' ms'
        else round(numeric_value / 1000, 3)::text || ' s'
      end
    when unit = 's' then
      case
        when numeric_value < 60 then numeric_value::text || ' s'
        else round(numeric_value / 60, 3)::text || ' min'
      end
    when unit = 'min' then numeric_value::text || ' min'
    else null
  end as pretty_value,
  unit as unit,
  category as category,
  vartype as vartype,
  case when is_default_bool then 1 else 0 end as is_default,
  1 as configured
from with_numeric
