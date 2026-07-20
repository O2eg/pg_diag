with sequence_acl as (
  select
    n.nspname as schema_name,
    c.relname as sequence_name,
    pg_catalog.pg_get_userbyid(c.relowner) as owner_name,
    acl.grantor,
    acl.grantee,
    acl.privilege_type,
    acl.is_grantable
  from pg_catalog.pg_class c
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  cross join lateral pg_catalog.aclexplode(
    coalesce(c.relacl, pg_catalog.acldefault('S', c.relowner))
  ) as acl
  where c.relkind = 'S'
    and n.nspname not in ('pg_catalog', 'information_schema', 'pg_toast')
    and n.nspname not like 'pg_temp_%'
    and n.nspname not like 'pg_toast_temp_%'
)
select
  schema_name,
  sequence_name,
  owner_name,
  case when grantee = 0 then 'PUBLIC' else pg_catalog.pg_get_userbyid(grantee) end as grantee,
  pg_catalog.pg_get_userbyid(grantor) as grantor,
  privilege_type,
  is_grantable,
  case
    when grantee = 0 and privilege_type in ('USAGE', 'UPDATE') then 'high'
    when grantee = 0 then 'medium'
    when is_grantable then 'medium'
    else 'ok'
  end as risk_level,
  case
    when grantee = 0 then 'sequence privilege is granted to PUBLIC'
    when is_grantable then 'sequence privilege can be granted onward'
    else 'informational sequence privilege'
  end as risk_reason
from sequence_acl
where grantee = 0
   or (is_grantable and pg_catalog.pg_get_userbyid(grantee) <> owner_name)
order by
  risk_level desc,
  schema_name asc,
  sequence_name asc,
  grantee asc,
  privilege_type asc
