select
    n.nspname as schema_name,
    c.relname as table_name,
    pg_catalog.pg_get_userbyid(c.relowner) as table_owner,
    coalesce(grantee.rolname, 'PUBLIC') as grantee_name,
    coalesce(grantee.rolcanlogin, false) as grantee_can_login,
    e.privilege_type,
    e.is_grantable,
    c.relforcerowsecurity as force_rls,
    case when e.grantee = 0 or e.is_grantable then 'high' else 'medium' end as risk_level,
    'RLS table has broad or directly granted table privileges that should be reviewed with policy coverage' as risk_reason
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
cross join lateral aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) e
left join pg_roles grantee on grantee.oid = e.grantee
where c.relkind in ('r', 'p')
  and c.relrowsecurity
  and e.grantee <> c.relowner
  and (e.grantee = 0 or e.is_grantable or coalesce(grantee.rolcanlogin, false))
  and n.nspname not in ('pg_catalog', 'information_schema')
  and n.nspname not like 'pg_toast%'
  and not exists (
      select 1 from pg_depend d
      where d.classid = 'pg_class'::regclass and d.objid = c.oid and d.deptype = 'e'
  )
order by risk_level desc, schema_name, table_name, grantee_name, privilege_type
