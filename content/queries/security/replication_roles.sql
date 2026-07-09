select
  rolname,
  rolcanlogin,
  rolconnlimit,
  rolsuper,
  rolcreatedb,
  rolcreaterole,
  rolreplication,
  rolbypassrls,
  case
    when rolsuper or rolcreaterole or rolbypassrls then 'high'
    when rolcreatedb then 'medium'
    else 'medium'
  end as risk_level,
  concat_ws(
    ', ',
    case when rolsuper then 'replication role is also superuser' end,
    case when rolcreaterole then 'replication role can create roles' end,
    case when rolcreatedb then 'replication role can create databases' end,
    case when rolbypassrls then 'replication role bypasses row level security' end,
    case when not rolcanlogin then 'replication role cannot login directly' end,
    'role has REPLICATION privilege'
  ) as risk_reason
from pg_catalog.pg_roles
where rolreplication
  and rolname !~ '^pg_'
order by
  risk_level desc,
  rolcanlogin desc,
  rolname asc
