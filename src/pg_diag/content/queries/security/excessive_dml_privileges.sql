select
  c.oid as relation_oid,
  case when acl.grantee = 0 then 'PUBLIC' else pg_catalog.pg_get_userbyid(acl.grantee) end as grantee,
  n.nspname as table_schema,
  c.relname as table_name,
  acl.privilege_type,
  acl.is_grantable,
  coalesce(grantee_role.rolsuper, false) as grantee_is_superuser,
  pg_catalog.pg_get_userbyid(c.relowner) as table_owner,
  case
    when acl.grantee = 0 and acl.privilege_type in ('DELETE', 'TRUNCATE', 'UPDATE') then 'high'
    when acl.grantee = 0 then 'medium'
    when acl.is_grantable then 'medium'
    else 'ok'
  end as risk_level,
  case
    when acl.grantee = 0 then 'DML privilege is granted to PUBLIC'
    when acl.is_grantable then 'DML privilege can be granted onward'
    else 'informational DML privilege'
  end as risk_reason
from pg_catalog.pg_class c
join pg_catalog.pg_namespace n on n.oid = c.relnamespace
cross join lateral pg_catalog.aclexplode(
  coalesce(c.relacl, pg_catalog.acldefault('r', c.relowner))
) acl
left join pg_catalog.pg_roles grantee_role on grantee_role.oid = acl.grantee
where c.relkind in ('r', 'p', 'v', 'f')
  and acl.privilege_type in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')
  and n.nspname not in ('pg_catalog', 'information_schema', 'pg_toast')
  and n.nspname not like 'pg_temp_%'
  and n.nspname not like 'pg_toast_temp_%'
  and (
    acl.grantee = 0
    or (acl.is_grantable and acl.grantee <> c.relowner)
  )
order by risk_level desc, n.nspname, c.relname, grantee, acl.privilege_type, c.oid
limit 1000
