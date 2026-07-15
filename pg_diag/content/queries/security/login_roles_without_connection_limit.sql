select
  rolname,
  rolconnlimit,
  rolsuper,
  rolcreatedb,
  rolcreaterole,
  rolreplication,
  rolbypassrls,
  'unknown' as risk_level,
  'No per-role connection limit is configured; pool and global connection controls determine whether this is a risk' as risk_reason
from pg_catalog.pg_roles
where rolcanlogin
  and rolconnlimit = -1
  and rolname !~ '^pg_'
order by
  rolsuper desc,
  rolreplication desc,
  rolname asc
