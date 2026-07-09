with wanted(name) as (
  values ('pgcrypto'), ('pgsodium')
),
extension_state as (
  select
    w.name,
    ae.default_version,
    ae.installed_version
  from wanted w
  left join pg_catalog.pg_available_extensions ae on ae.name = w.name
),
summary as (
  select
    coalesce(string_agg(name, ', ' order by name) filter (where default_version is not null), '') as available_extensions,
    coalesce(string_agg(name, ', ' order by name) filter (where installed_version is not null), '') as installed_extensions,
    bool_or(default_version is not null) as has_available_extension,
    bool_or(installed_version is not null) as has_installed_extension
  from extension_state
)
select
  'cryptographic_extensions' as check_name,
  available_extensions,
  installed_extensions,
  case
    when not has_available_extension then 'high'
    else 'medium'
  end as risk_level,
  case
    when not has_available_extension then 'no pgcrypto or pgsodium extension is available on this server'
    else 'no pgcrypto or pgsodium extension is installed in the connected database'
  end as risk_reason
from summary
where not has_installed_extension
order by check_name asc
