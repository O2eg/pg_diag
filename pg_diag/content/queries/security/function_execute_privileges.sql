with function_acl as (
  select
    p.oid as function_oid,
    n.nspname as schema_name,
    p.proname as function_name,
    pg_catalog.pg_get_function_identity_arguments(p.oid) as function_signature,
    pg_catalog.pg_get_userbyid(p.proowner) as owner_name,
    p.prosecdef as is_security_definer,
    exists (
      select 1
      from unnest(coalesce(p.proconfig, array[]::text[])) as config(setting)
      where lower(setting) like 'search_path=%'
    ) as has_search_path_config,
    l.lanname as language_name,
    acl.grantor,
    acl.grantee,
    acl.privilege_type,
    acl.is_grantable
  from pg_catalog.pg_proc p
  join pg_catalog.pg_namespace n on n.oid = p.pronamespace
  join pg_catalog.pg_language l on l.oid = p.prolang
  cross join lateral pg_catalog.aclexplode(
    coalesce(p.proacl, pg_catalog.acldefault('f', p.proowner))
  ) as acl
  where n.nspname not in ('pg_catalog', 'information_schema', 'pg_toast')
    and n.nspname not like 'pg_temp_%'
    and n.nspname not like 'pg_toast_temp_%'
    and not exists (
      select 1
      from pg_catalog.pg_depend d
      where d.classid = 'pg_proc'::regclass
        and d.objid = p.oid
        and d.deptype = 'e'
    )
)
select
  function_oid,
  schema_name,
  function_name,
  function_signature,
  owner_name,
  case when grantee = 0 then 'PUBLIC' else pg_catalog.pg_get_userbyid(grantee) end as grantee,
  pg_catalog.pg_get_userbyid(grantor) as grantor,
  privilege_type,
  is_grantable,
  is_security_definer,
  language_name,
  case
    when grantee = 0 and is_security_definer and not has_search_path_config then 'high'
    when grantee = 0 and is_security_definer then 'medium'
    when grantee = 0 then 'ok'
    when is_grantable then 'medium'
    else 'ok'
  end as risk_level,
  case
    when grantee = 0 and is_security_definer and not has_search_path_config then 'PUBLIC can execute SECURITY DEFINER function without a function-local search_path'
    when grantee = 0 and is_security_definer then 'PUBLIC can execute SECURITY DEFINER function; review the function body and configured search_path'
    when grantee = 0 then 'PUBLIC EXECUTE is the PostgreSQL default for functions; shown for inventory'
    when is_grantable then 'function EXECUTE privilege can be granted onward'
    else 'informational function privilege'
  end as risk_reason
from function_acl
where privilege_type = 'EXECUTE'
  and (
    grantee = 0
    or (is_grantable and pg_catalog.pg_get_userbyid(grantee) <> owner_name)
  )
order by
  risk_level desc,
  schema_name asc,
  function_name asc,
  function_signature asc,
  grantee asc
limit 1000
