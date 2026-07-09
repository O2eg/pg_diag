select
  rolname,
  rolconnlimit,
  rolsuper,
  rolcreatedb,
  rolcreaterole,
  rolreplication,
  rolbypassrls,
  case
    when rolsuper or rolbypassrls or rolcreaterole or rolreplication then 'medium'
    else 'medium'
  end as risk_level,
  'login role has no per-role connection limit' as risk_reason
from pg_catalog.pg_roles
where rolcanlogin
  and rolconnlimit = -1
  and rolname !~ '^pg_'
order by
  rolsuper desc,
  rolreplication desc,
  rolname asc
