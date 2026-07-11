with wanted(name) as (
  values ('anon'), ('pg_anonymize')
),
settings as (
  select setting as session_preload_libraries
  from pg_catalog.pg_settings
  where name = 'session_preload_libraries'
),
extension_state as (
  select
    w.name,
    ae.default_version,
    ae.installed_version,
    w.name = any(
      regexp_split_to_array(lower(coalesce(s.session_preload_libraries, '')), '\\s*,\\s*')
    ) as is_preloaded
  from wanted w
  cross join settings s
  left join pg_catalog.pg_available_extensions ae on ae.name = w.name
),
summary as (
  select
    s.session_preload_libraries,
    coalesce(string_agg(es.name, ', ' order by es.name) filter (where es.default_version is not null), '') as available_extensions,
    coalesce(string_agg(es.name, ', ' order by es.name) filter (where es.installed_version is not null), '') as installed_extensions,
    coalesce(string_agg(es.name, ', ' order by es.name) filter (where es.is_preloaded), '') as preloaded_extensions,
    bool_or(es.default_version is not null) as has_available_extension,
    bool_or(es.installed_version is not null) as has_installed_extension,
    bool_or(es.is_preloaded) as has_preloaded_extension
  from settings s
  cross join extension_state es
  group by s.session_preload_libraries
)
select
  'anonymization_extensions' as check_name,
  session_preload_libraries,
  available_extensions,
  installed_extensions,
  preloaded_extensions,
  'unknown' as risk_level,
  case
    when not has_available_extension then 'no anon or pg_anonymize extension is available on this server'
    else 'no anon or pg_anonymize extension is installed or preloaded for the connected database'
  end as risk_reason
from summary
where not has_installed_extension
  and not has_preloaded_extension
order by check_name asc
