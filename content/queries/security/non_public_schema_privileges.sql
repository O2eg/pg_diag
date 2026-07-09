with expanded_acl as (
  select
    n.oid,
    n.nspname,
    n.nspowner,
    acl.grantor,
    acl.grantee,
    acl.privilege_type,
    acl.is_grantable
  from pg_catalog.pg_namespace n
  cross join lateral pg_catalog.aclexplode(
    coalesce(n.nspacl, pg_catalog.acldefault('n', n.nspowner))
  ) as acl
  where n.nspname <> 'public'
    and n.nspname not in ('pg_catalog', 'information_schema', 'pg_toast')
    and n.nspname not like 'pg_%'
    and n.nspname not like 'pg_temp_%'
    and n.nspname not like 'pg_toast_temp_%'
)
select
  nspname as schema_name,
  pg_catalog.pg_get_userbyid(nspowner) as schema_owner,
  case when grantee = 0 then 'PUBLIC' else pg_catalog.pg_get_userbyid(grantee) end as grantee,
  pg_catalog.pg_get_userbyid(grantor) as grantor,
  privilege_type,
  is_grantable,
  case
    when grantee = 0 and privilege_type = 'CREATE' then 'high'
    when grantee = 0 then 'medium'
    when privilege_type = 'CREATE' then 'medium'
    when is_grantable then 'medium'
    else 'ok'
  end as risk_level,
  case
    when grantee = 0 and privilege_type = 'CREATE' then 'PUBLIC can create objects in a non-public schema'
    when grantee = 0 then 'PUBLIC has privileges on a non-public schema'
    when privilege_type = 'CREATE' then 'non-owner role can create objects in schema'
    when is_grantable then 'schema privilege can be granted onward'
    else 'informational schema privilege'
  end as risk_reason
from expanded_acl
where grantee = 0
   or (privilege_type = 'CREATE' and grantee <> nspowner)
   or (is_grantable and grantee <> nspowner)
order by
  risk_level desc,
  schema_name asc,
  grantee asc,
  privilege_type asc
