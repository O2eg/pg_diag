with relation_acls as (
    select
        n.nspname as schema_name,
        case c.relkind
            when 'r' then 'table'
            when 'p' then 'partitioned_table'
            when 'S' then 'sequence'
            when 'v' then 'view'
            when 'm' then 'materialized_view'
            when 'f' then 'foreign_table'
            else c.relkind::text
        end as object_kind,
        c.relname as object_name,
        md5(coalesce((
            select string_agg(
                coalesce(grantee.rolname, 'PUBLIC') || ':' || e.privilege_type || ':' || e.is_grantable::text,
                ',' order by coalesce(grantee.rolname, 'PUBLIC'), e.privilege_type, e.is_grantable
            )
            from aclexplode(coalesce(c.relacl, acldefault((case when c.relkind = 'S' then 'S' else 'r' end)::"char", c.relowner))) e
            left join pg_roles grantee on grantee.oid = e.grantee
        ), '<default>')) as acl_signature
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where c.relkind in ('r', 'p', 'S', 'v', 'm', 'f')
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
      and not exists (
          select 1 from pg_depend d
          where d.classid = 'pg_class'::regclass and d.objid = c.oid and d.deptype = 'e'
      )
),
function_acls as (
    select
        n.nspname as schema_name,
        'function' as object_kind,
        p.proname as object_name,
        md5(coalesce((
            select string_agg(
                coalesce(grantee.rolname, 'PUBLIC') || ':' || e.privilege_type || ':' || e.is_grantable::text,
                ',' order by coalesce(grantee.rolname, 'PUBLIC'), e.privilege_type, e.is_grantable
            )
            from aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) e
            left join pg_roles grantee on grantee.oid = e.grantee
        ), '<default>')) as acl_signature
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
      and not exists (
          select 1 from pg_depend d
          where d.classid = 'pg_proc'::regclass and d.objid = p.oid and d.deptype = 'e'
      )
),
objects as (
    select * from relation_acls
    union all
    select * from function_acls
)
select
    schema_name,
    object_kind,
    count(*) as object_count,
    count(distinct acl_signature) as acl_signature_count,
    array_to_string((array_agg(object_name order by object_name))[1:10], ', ') as sample_objects,
    'unknown' as risk_level,
    'Objects of the same kind in one schema have different ACL signatures; compare with the intended privilege baseline' as risk_reason
from objects
group by schema_name, object_kind
having count(distinct acl_signature) > 1
order by schema_name, object_kind
