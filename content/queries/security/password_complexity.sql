with wanted_modules(module_name) as (
  values ('passwordcheck'), ('credcheck')
),
settings as (
  select setting as shared_preload_libraries
  from pg_catalog.pg_settings
  where name = 'shared_preload_libraries'
),
module_state as (
  select
    w.module_name,
    lower(coalesce(s.shared_preload_libraries, '')) like '%' || w.module_name || '%' as is_preloaded,
    ae.installed_version is not null as is_installed,
    ae.default_version is not null as is_available
  from wanted_modules w
  cross join settings s
  left join pg_catalog.pg_available_extensions ae on ae.name = w.module_name
),
summary as (
  select
    s.shared_preload_libraries,
    coalesce(string_agg(ms.module_name, ', ' order by ms.module_name) filter (where ms.is_preloaded), '') as preloaded_modules,
    coalesce(string_agg(ms.module_name, ', ' order by ms.module_name) filter (where ms.is_installed), '') as installed_modules,
    coalesce(string_agg(ms.module_name, ', ' order by ms.module_name) filter (where ms.is_available), '') as available_modules,
    bool_or(ms.is_preloaded) as has_active_complexity_hook
  from settings s
  cross join module_state ms
  group by s.shared_preload_libraries
)
select
  'password_complexity' as check_name,
  shared_preload_libraries,
  preloaded_modules,
  installed_modules,
  available_modules,
  'medium' as risk_level,
  'password complexity extension is not active in shared_preload_libraries' as risk_reason
from summary
where not has_active_complexity_hook
order by check_name asc
