select
  n.nspname as schema_name,
  p.proname as function_name,
  pg_catalog.pg_get_function_identity_arguments(p.oid) as function_signature,
  pg_catalog.pg_get_userbyid(p.proowner) as owner_name,
  coalesce(owner_role.rolsuper, false) as owner_is_superuser,
  l.lanname as language_name,
  array_to_string(p.proconfig, ', ') as function_config,
  exists (
    select 1
    from unnest(coalesce(p.proconfig, array[]::text[])) as config(setting)
    where lower(setting) like 'search_path=%'
  ) as has_search_path_config,
  case
    when coalesce(owner_role.rolsuper, false)
      and not exists (
        select 1
        from unnest(coalesce(p.proconfig, array[]::text[])) as config(setting)
        where lower(setting) like 'search_path=%'
      )
      then 'high'
    when coalesce(owner_role.rolsuper, false) then 'medium'
    when not exists (
        select 1
        from unnest(coalesce(p.proconfig, array[]::text[])) as config(setting)
        where lower(setting) like 'search_path=%'
      )
      then 'medium'
    else 'medium'
  end as risk_level,
  concat_ws(
    ', ',
    case when coalesce(owner_role.rolsuper, false) then 'owned by superuser' end,
    case when not exists (
        select 1
        from unnest(coalesce(p.proconfig, array[]::text[])) as config(setting)
        where lower(setting) like 'search_path=%'
      ) then 'no function-local search_path' end,
    'SECURITY DEFINER executes with owner privileges'
  ) as risk_reason
from pg_catalog.pg_proc p
join pg_catalog.pg_namespace n on n.oid = p.pronamespace
join pg_catalog.pg_language l on l.oid = p.prolang
left join pg_catalog.pg_roles owner_role on owner_role.oid = p.proowner
where p.prosecdef
  and n.nspname not in ('pg_catalog', 'information_schema', 'pg_toast')
  and n.nspname not like 'pg_temp_%'
  and n.nspname not like 'pg_toast_temp_%'
  and not exists (
    select 1
    from pg_catalog.pg_depend d
    where d.classid = 'pg_proc'::regclass
      and d.objid = p.oid
      and d.deptype = 'e'
  )
order by
  risk_level desc,
  n.nspname asc,
  p.proname asc,
  function_signature asc
