with public_schema as (
  select
    oid,
    nspname,
    nspowner,
    nspacl
  from pg_catalog.pg_namespace
  where nspname = 'public'
),
expanded_acl_bounded as (
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
  where (acl.grantee = 0 and acl.privilege_type = 'CREATE')
    or (acl.privilege_type = 'CREATE' and acl.grantee <> ps.nspowner)
    or (acl.is_grantable and acl.grantee <> ps.nspowner)
  limit 3001
),
expanded_acl as (
  select * from expanded_acl_bounded limit 3000
),
coverage as (
  select count(*) > 3000 as acl_expansion_truncated
  from expanded_acl_bounded
)
select
  current_database()::text as database_name,
  expanded_acl.nspname::text as schema_name,
  pg_catalog.pg_get_userbyid(expanded_acl.nspowner)::text as schema_owner,
  case when expanded_acl.grantee = 0 then 'PUBLIC' else pg_catalog.pg_get_userbyid(expanded_acl.grantee)::text end as grantee,
  pg_catalog.pg_get_userbyid(expanded_acl.grantor)::text as grantor,
  expanded_acl.privilege_type,
  expanded_acl.is_grantable,
  coverage.acl_expansion_truncated,
  case
    when expanded_acl.grantee = 0 and expanded_acl.privilege_type = 'CREATE' then 'high'
    when expanded_acl.privilege_type = 'CREATE' then 'medium'
    when expanded_acl.is_grantable then 'medium'
    else 'ok'
  end as risk_level,
  case
    when coverage.acl_expansion_truncated then 'Public-schema privilege is part of a truncated ACL expansion; review the coverage flag before treating the inventory as complete'
    when expanded_acl.grantee = 0 and expanded_acl.privilege_type = 'CREATE' then 'PUBLIC can create objects in schema public'
    when expanded_acl.privilege_type = 'CREATE' then 'non-owner role can create objects in schema public'
    when expanded_acl.is_grantable then 'privilege can be granted onward'
    else 'informational grant'
  end as risk_reason
from expanded_acl
cross join coverage
union all
select
  current_database()::text,
  '[coverage]'::text,
  ''::text,
  ''::text,
  ''::text,
  ''::text,
  false,
  coverage.acl_expansion_truncated,
  'unknown'::text,
  'The public-schema ACL expansion exceeded 3000 rows; absence of privilege findings is not a clean result'::text
from coverage
where coverage.acl_expansion_truncated
order by risk_level desc, grantee asc, privilege_type asc
