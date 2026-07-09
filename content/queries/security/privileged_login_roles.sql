select
  rolname,
  rolconnlimit,
  rolsuper,
  rolcreatedb,
  rolcreaterole,
  rolreplication,
  rolbypassrls,
  case
    when rolsuper or rolbypassrls or rolcreaterole then 'high'
    when rolreplication or rolcreatedb then 'medium'
    else 'ok'
  end as risk_level,
  concat_ws(
    ', ',
    case when rolsuper then 'superuser' end,
    case when rolcreaterole then 'can create roles' end,
    case when rolcreatedb then 'can create databases' end,
    case when rolreplication then 'can initiate replication' end,
    case when rolbypassrls then 'bypasses row level security' end
  ) as risk_reason
from pg_catalog.pg_roles
where rolcanlogin
  and (rolsuper or rolcreatedb or rolcreaterole or rolreplication or rolbypassrls)
order by
  rolsuper desc,
  rolbypassrls desc,
  rolcreaterole desc,
  rolreplication desc,
  rolcreatedb desc,
  rolname asc
