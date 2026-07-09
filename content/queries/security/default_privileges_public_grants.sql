with expanded_default_acl as (
  select
    d.defaclrole,
    d.defaclnamespace,
    d.defaclobjtype,
    acl.grantor,
    acl.grantee,
    acl.privilege_type,
    acl.is_grantable
  from pg_catalog.pg_default_acl d
  cross join lateral pg_catalog.aclexplode(d.defaclacl) as acl
),
normalized as (
  select
    pg_catalog.pg_get_userbyid(defaclrole) as owner_name,
    case
      when defaclnamespace = 0 then '<all schemas>'
      else defaclnamespace::regnamespace::text
    end as schema_name,
    case defaclobjtype
      when 'r' then 'tables'
      when 'S' then 'sequences'
      when 'f' then 'functions'
      when 'T' then 'types'
      when 'n' then 'schemas'
      else defaclobjtype::text
    end as object_type,
    case when grantee = 0 then 'PUBLIC' else pg_catalog.pg_get_userbyid(grantee) end as grantee,
    pg_catalog.pg_get_userbyid(grantor) as grantor,
    privilege_type,
    is_grantable
  from expanded_default_acl
)
select
  owner_name,
  schema_name,
  object_type,
  grantee,
  grantor,
  privilege_type,
  is_grantable,
  case
    when grantee = 'PUBLIC' and privilege_type in ('CREATE', 'EXECUTE', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'USAGE') then 'high'
    when grantee = 'PUBLIC' then 'medium'
    when is_grantable then 'medium'
    else 'ok'
  end as risk_level,
  case
    when grantee = 'PUBLIC' then 'future objects will grant privileges to PUBLIC'
    when is_grantable then 'future object privilege can be granted onward'
    else 'informational default privilege'
  end as risk_reason
from normalized
where grantee = 'PUBLIC'
   or (is_grantable and grantee <> owner_name)
order by
  risk_level desc,
  owner_name asc,
  schema_name asc,
  object_type asc,
  grantee asc,
  privilege_type asc
