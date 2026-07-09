with risky_extensions(extension_name, risk_level, risk_reason) as (
  values
    ('dblink', 'high', 'extension can open database connections from SQL and may bridge trust boundaries'),
    ('file_fdw', 'high', 'extension can expose server-side files through foreign tables'),
    ('adminpack', 'high', 'extension exposes server administration helper functions'),
    ('postgres_fdw', 'medium', 'extension can access remote PostgreSQL servers and should be reviewed'),
    ('plpython3u', 'high', 'untrusted procedural language can execute operating system actions'),
    ('plperlu', 'high', 'untrusted procedural language can execute operating system actions'),
    ('pltclu', 'high', 'untrusted procedural language can execute operating system actions')
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
    'high' as risk_level,
    'untrusted procedural language is installed' as risk_reason
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
