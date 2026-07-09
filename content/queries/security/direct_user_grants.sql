with grants as (
    select
        case c.relkind when 'S' then 'sequence' else 'relation' end as object_kind,
        n.nspname as schema_name,
        c.relname as object_name,
        pg_catalog.pg_get_userbyid(c.relowner) as owner_name,
        grantee.rolname as grantee_name,
        e.privilege_type,
        e.is_grantable
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    cross join lateral aclexplode(coalesce(c.relacl, acldefault((case when c.relkind = 'S' then 'S' else 'r' end)::"char", c.relowner))) e
    join pg_roles grantee on grantee.oid = e.grantee and grantee.rolcanlogin
    where c.relkind in ('r', 'p', 'S', 'v', 'm', 'f')
      and e.grantee <> c.relowner
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
      and not exists (
          select 1 from pg_depend d
          where d.classid = 'pg_class'::regclass and d.objid = c.oid and d.deptype = 'e'
      )
    union all
    select
        'function',
        n.nspname,
        p.proname,
        pg_catalog.pg_get_userbyid(p.proowner),
        grantee.rolname,
        e.privilege_type,
        e.is_grantable
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) e
    join pg_roles grantee on grantee.oid = e.grantee and grantee.rolcanlogin
    where e.grantee <> p.proowner
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
      and not exists (
          select 1 from pg_depend d
          where d.classid = 'pg_proc'::regclass and d.objid = p.oid and d.deptype = 'e'
      )
    union all
    select
        'schema',
        n.nspname,
        n.nspname,
        pg_catalog.pg_get_userbyid(n.nspowner),
        grantee.rolname,
        e.privilege_type,
        e.is_grantable
    from pg_namespace n
    cross join lateral aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) e
    join pg_roles grantee on grantee.oid = e.grantee and grantee.rolcanlogin
    where e.grantee <> n.nspowner
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
)
select
    object_kind,
    schema_name,
    object_name,
    owner_name,
    grantee_name,
    privilege_type,
    is_grantable,
    'medium' as risk_level,
    'Privilege is granted directly to a login role instead of a group role' as risk_reason
from grants
order by schema_name, object_kind, object_name, grantee_name, privilege_type
