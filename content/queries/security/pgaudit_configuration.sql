with settings as (
  select
    max(setting) filter (where name = 'shared_preload_libraries') as shared_preload_libraries,
    max(setting) filter (where name = 'pgaudit.log') as pgaudit_log,
    max(source) filter (where name = 'pgaudit.log') as pgaudit_log_source
  from pg_catalog.pg_settings
  where name in ('shared_preload_libraries', 'pgaudit.log')
),
extension_state as (
  select exists (
    select 1
    from pg_catalog.pg_extension
    where extname = 'pgaudit'
  ) as pgaudit_extension_created
),
evaluated as (
  select
    s.shared_preload_libraries,
    s.pgaudit_log,
    s.pgaudit_log_source,
    lower(coalesce(s.shared_preload_libraries, '')) like '%pgaudit%' as pgaudit_preloaded,
    e.pgaudit_extension_created
  from settings s
  cross join extension_state e
)
select
  shared_preload_libraries,
  pgaudit_preloaded,
  pgaudit_extension_created,
  pgaudit_log,
  pgaudit_log_source,
  case
    when not pgaudit_preloaded then 'medium'
    when coalesce(nullif(pgaudit_log, ''), 'none') = 'none' then 'medium'
    else 'ok'
  end as risk_level,
  case
    when not pgaudit_preloaded then 'pgAudit is not loaded through shared_preload_libraries'
    when coalesce(nullif(pgaudit_log, ''), 'none') = 'none' then 'pgAudit is loaded but pgaudit.log is not configured'
    else 'pgAudit configuration is informational'
  end as risk_reason
from evaluated
where not pgaudit_preloaded
   or coalesce(nullif(pgaudit_log, ''), 'none') = 'none'
order by risk_level desc
