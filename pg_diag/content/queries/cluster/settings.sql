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
    pending_restart,
    case
      when name in ('lock_timeout', 'statement_timeout') and reset_val = boot_val then 'default'
      when name in ('lock_timeout', 'statement_timeout') then 'pre-collector value'
      else source
    end as effective_source,
    context,
    sourcefile,
    sourceline,
    boot_val,
    reset_val,
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
    when numeric_value is null or numeric_value < 0 then null
    when unit = '8kB' then numeric_value * 8192
    when unit = 'kB' then numeric_value * 1024
    when unit = 'MB' then numeric_value * 1024 * 1024
    when unit = 'GB' then numeric_value * 1024 * 1024 * 1024
    when unit = 'B' then numeric_value
    when unit = 'ms' then numeric_value / 1000
    when unit = 's' then numeric_value
    when unit = 'min' then numeric_value * 60
    else numeric_value
  end as setting_normalized,
  case
    when numeric_value is null or numeric_value < 0 then null
    when unit in ('8kB', 'kB', 'MB', 'GB', 'B') then 'bytes'
    when unit in ('ms', 's', 'min') then 'seconds'
    when unit is null then 'none'
    else 'none'
  end as unit_normalized,
  case
    when numeric_value is null or numeric_value < 0 then null
    when unit in ('8kB', 'kB', 'MB', 'GB', 'B') then 'data_volume'
    when unit in ('ms', 's', 'min') then 'seconds'
    else 'measurement'
  end as quantity_normalized,
  unit as source_unit,
  pending_restart as pending_restart,
  category as category,
  vartype as vartype,
  effective_source as source,
  context,
  sourcefile,
  sourceline,
  boot_val,
  reset_val,
  is_default_bool as is_default,
  case
    when pending_restart then 'medium'
    when name = 'work_mem' and is_default_bool then 'medium'
    else 'ok'
  end as pg_diag_internal_severity,
  concat_ws(
    '; ',
    case when pending_restart then 'setting change is pending a PostgreSQL restart' end,
    case
      when name = 'work_mem' and is_default_bool
        then 'work_mem remains at the PostgreSQL default; validate it against the workload before tuning'
    end
  ) as pg_diag_internal_reason
from with_numeric
