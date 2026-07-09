select
    seq_ns.nspname as sequence_schema,
    seq.relname as sequence_name,
    pg_catalog.pg_get_userbyid(seq.relowner) as sequence_owner,
    tbl_ns.nspname as table_schema,
    tbl.relname as table_name,
    att.attname as column_name,
    pg_catalog.pg_get_userbyid(tbl.relowner) as table_owner,
    'medium' as risk_level,
    'Sequence owner differs from the dependent table owner' as risk_reason
from pg_class seq
join pg_namespace seq_ns on seq_ns.oid = seq.relnamespace
join pg_depend dep
  on dep.classid = 'pg_class'::regclass
 and dep.objid = seq.oid
 and dep.deptype in ('a', 'i')
join pg_class tbl
  on dep.refclassid = 'pg_class'::regclass
 and dep.refobjid = tbl.oid
join pg_namespace tbl_ns on tbl_ns.oid = tbl.relnamespace
join pg_attribute att
  on att.attrelid = tbl.oid
 and att.attnum = dep.refobjsubid
where seq.relkind = 'S'
  and tbl.relkind in ('r', 'p')
  and seq.relowner <> tbl.relowner
  and seq_ns.nspname not in ('pg_catalog', 'information_schema')
  and seq_ns.nspname not like 'pg_toast%'
  and tbl_ns.nspname not in ('pg_catalog', 'information_schema')
  and tbl_ns.nspname not like 'pg_toast%'
order by sequence_schema, sequence_name
