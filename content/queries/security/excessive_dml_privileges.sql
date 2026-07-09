select
  tp.grantee,
  tp.table_schema,
  tp.table_name,
  tp.privilege_type,
  tp.is_grantable,
  coalesce(r.rolsuper, false) as grantee_is_superuser,
  pg_catalog.pg_get_userbyid(c.relowner) as table_owner,
  case
    when tp.grantee = 'PUBLIC' and tp.privilege_type in ('DELETE', 'TRUNCATE', 'UPDATE') then 'high'
    when tp.grantee = 'PUBLIC' then 'medium'
    when tp.is_grantable = 'YES' then 'medium'
    else 'ok'
  end as risk_level,
  case
    when tp.grantee = 'PUBLIC' then 'DML privilege is granted to PUBLIC'
    when tp.is_grantable = 'YES' then 'DML privilege can be granted onward'
    else 'informational DML privilege'
  end as risk_reason
from information_schema.table_privileges tp
join pg_catalog.pg_namespace n on n.nspname = tp.table_schema
join pg_catalog.pg_class c on c.relnamespace = n.oid and c.relname = tp.table_name
left join pg_catalog.pg_roles r on r.rolname = tp.grantee
where tp.privilege_type in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')
  and tp.table_schema not in ('pg_catalog', 'information_schema', 'pg_toast')
  and tp.table_schema not like 'pg_temp_%'
  and tp.table_schema not like 'pg_toast_temp_%'
  and (
    tp.grantee = 'PUBLIC'
    or (
      tp.is_grantable = 'YES'
      and tp.grantee <> pg_catalog.pg_get_userbyid(c.relowner)
    )
  )
order by
  risk_level desc,
  tp.table_schema asc,
  tp.table_name asc,
  tp.grantee asc,
  tp.privilege_type asc
