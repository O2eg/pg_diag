with public_schema as (
  select
    oid,
    nspname,
    nspowner,
    nspacl
  from pg_catalog.pg_namespace
  where nspname = 'public'
),
expanded_acl as (
  select
    ps.oid,
    ps.nspname,
    ps.nspowner,
    acl.grantor,
    acl.grantee,
    acl.privilege_type,
    acl.is_grantable
  from public_schema ps
  cross join lateral pg_catalog.aclexplode(
    coalesce(ps.nspacl, pg_catalog.acldefault('n', ps.nspowner))
  ) as acl
)
select
  current_database() as database_name,
  nspname as schema_name,
  pg_catalog.pg_get_userbyid(nspowner) as schema_owner,
  case when grantee = 0 then 'PUBLIC' else pg_catalog.pg_get_userbyid(grantee) end as grantee,
  pg_catalog.pg_get_userbyid(grantor) as grantor,
  privilege_type,
  is_grantable,
  case
    when grantee = 0 and privilege_type = 'CREATE' then 'high'
    when privilege_type = 'CREATE' then 'medium'
    when is_grantable then 'medium'
    else 'ok'
  end as risk_level,
  case
    when grantee = 0 and privilege_type = 'CREATE' then 'PUBLIC can create objects in schema public'
    when privilege_type = 'CREATE' then 'non-owner role can create objects in schema public'
    when is_grantable then 'privilege can be granted onward'
    else 'informational grant'
  end as risk_reason
from expanded_acl
where (grantee = 0 and privilege_type = 'CREATE')
  or (privilege_type = 'CREATE' and grantee <> nspowner)
  or (is_grantable and grantee <> nspowner)
order by
  risk_level desc,
  grantee asc,
  privilege_type asc
