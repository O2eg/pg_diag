with extension_relations as (
    select
        e.extname as extension_name,
        'relation' as object_kind,
        n.nspname as schema_name,
        c.relname as object_name,
        c.relacl::text as acl_text
    from pg_extension e
    join pg_depend d on d.refclassid = 'pg_extension'::regclass and d.refobjid = e.oid and d.deptype = 'e'
    join pg_class c on d.classid = 'pg_class'::regclass and d.objid = c.oid
    join pg_namespace n on n.oid = c.relnamespace
    where c.relacl is not null
),
extension_functions as (
    select
        e.extname as extension_name,
        'function' as object_kind,
        n.nspname as schema_name,
        p.proname as object_name,
        p.proacl::text as acl_text
    from pg_extension e
    join pg_depend d on d.refclassid = 'pg_extension'::regclass and d.refobjid = e.oid and d.deptype = 'e'
    join pg_proc p on d.classid = 'pg_proc'::regclass and d.objid = p.oid
    join pg_namespace n on n.oid = p.pronamespace
    where p.proacl is not null
)
select
    extension_name,
    object_kind,
    schema_name,
    object_name,
    acl_text,
    'unknown' as risk_level,
    'Extension-owned object has an explicit ACL entry; compare it with the extension and privilege baselines' as risk_reason
from (
    select * from extension_relations
    union all
    select * from extension_functions
) objects
order by extension_name, schema_name, object_kind, object_name
limit 1000
