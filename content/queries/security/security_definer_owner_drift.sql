select
    n.nspname as schema_name,
    p.proname as function_name,
    pg_get_function_identity_arguments(p.oid) as function_arguments,
    pg_catalog.pg_get_userbyid(p.proowner) as function_owner,
    pg_catalog.pg_get_userbyid(n.nspowner) as schema_owner,
    r.rolsuper as owner_is_superuser,
    case when r.rolsuper then 'high' else 'medium' end as risk_level,
    case
        when r.rolsuper then 'SECURITY DEFINER function is owned by a superuser'
        else 'SECURITY DEFINER function owner differs from the containing schema owner'
    end as risk_reason
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
join pg_roles r on r.oid = p.proowner
where p.prosecdef
  and n.nspname not in ('pg_catalog', 'information_schema')
  and n.nspname not like 'pg_toast%'
  and (r.rolsuper or p.proowner <> n.nspowner)
  and not exists (
      select 1 from pg_depend d
      where d.classid = 'pg_proc'::regclass and d.objid = p.oid and d.deptype = 'e'
  )
order by risk_level desc, schema_name, function_name
