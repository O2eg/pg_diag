with risky_extensions(extension_name, risk_level, risk_reason) as (
  values
    ('dblink', 'unknown', 'extension can open database connections from SQL; review function grants and stored credentials'),
    ('file_fdw', 'medium', 'extension can expose server-side files; review server definitions and privileges'),
    ('adminpack', 'medium', 'extension exposes server administration helpers; review function grants'),
    ('postgres_fdw', 'unknown', 'extension can access remote PostgreSQL servers; review user mappings and privileges'),
    ('plpython3u', 'medium', 'untrusted procedural language can execute operating system actions when used by a superuser'),
    ('plperlu', 'medium', 'untrusted procedural language can execute operating system actions when used by a superuser'),
    ('pltclu', 'medium', 'untrusted procedural language can execute operating system actions when used by a superuser')
),
extension_findings as (
  select
    'extension' as object_kind,
    e.extname as object_name,
    n.nspname as schema_name,
    e.extversion as version,
    r.risk_level,
    r.risk_reason
  from pg_catalog.pg_extension e
  join pg_catalog.pg_namespace n on n.oid = e.extnamespace
  join risky_extensions r on r.extension_name = e.extname
),
language_findings as (
  select
    'language' as object_kind,
    l.lanname as object_name,
    '' as schema_name,
    '' as version,
    'medium' as risk_level,
    'untrusted procedural language is installed; only trusted function ownership and CREATE privileges make its use acceptable' as risk_reason
  from pg_catalog.pg_language l
  where not l.lanpltrusted
    and l.lanname not in ('internal', 'c')
)
select *
from extension_findings
union all
select *
from language_findings
order by
  risk_level desc,
  object_kind asc,
  object_name asc
