select
    n.nspname as schema_name,
    c.relname as table_name,
    pg_catalog.pg_get_userbyid(c.relowner) as table_owner,
    coalesce(grantee.rolname, 'PUBLIC') as grantee_name,
    e.privilege_type,
    e.is_grantable,
    coalesce(s.seq_scan, 0) + coalesce(s.idx_scan, 0) as read_activity,
    coalesce(s.n_tup_ins, 0) + coalesce(s.n_tup_upd, 0) + coalesce(s.n_tup_del, 0) as write_activity,
    case when e.grantee = 0 or e.is_grantable then 'high' else 'medium' end as risk_level,
    'Powerful table privilege exists on a table with no observed activity since stats reset; verify whether it can be revoked' as risk_reason
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
left join pg_stat_user_tables s on s.relid = c.oid
cross join lateral aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) e
left join pg_roles grantee on grantee.oid = e.grantee
where c.relkind in ('r', 'p')
  and e.grantee <> c.relowner
  and e.privilege_type in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER')
  and coalesce(s.seq_scan, 0) + coalesce(s.idx_scan, 0) + coalesce(s.n_tup_ins, 0) + coalesce(s.n_tup_upd, 0) + coalesce(s.n_tup_del, 0) = 0
  and n.nspname not in ('pg_catalog', 'information_schema')
  and n.nspname not like 'pg_toast%'
  and not exists (
      select 1 from pg_depend d
      where d.classid = 'pg_class'::regclass and d.objid = c.oid and d.deptype = 'e'
  )
order by risk_level desc, schema_name, table_name, grantee_name, privilege_type
