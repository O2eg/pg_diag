select
  oid as role_oid,
  rolname,
  rolcanlogin,
  rolconnlimit,
  rolsuper,
  rolcreatedb,
  rolcreaterole,
  rolreplication,
  rolbypassrls,
  case
    when oid = 10 then 'ok'
    when rolsuper then 'high'
    when rolcreaterole or rolcreatedb or rolbypassrls then 'medium'
    else 'ok'
  end as risk_level,
  concat_ws(
    ', ',
    case when oid <> 10 and rolsuper then 'replication role is also superuser' end,
    case when oid <> 10 and rolcreaterole then 'replication role can create roles' end,
    case when oid <> 10 and rolcreatedb then 'replication role can create databases' end,
    case when oid <> 10 and rolbypassrls then 'replication role bypasses row level security' end,
    case when not rolcanlogin then 'replication role cannot login directly' end,
    case when oid = 10 then 'bootstrap superuser is the expected cluster owner' end,
    case
      when oid <> 10 and not (rolsuper or rolcreaterole or rolcreatedb or rolbypassrls)
        then 'dedicated replication privilege'
    end
  ) as risk_reason
from pg_catalog.pg_roles
where rolreplication
  and rolname !~ '^pg_'
order by
  risk_level desc,
  rolcanlogin desc,
  rolname asc
