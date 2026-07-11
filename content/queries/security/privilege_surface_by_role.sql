with explicit_grants as (
    select
        coalesce(grantee.rolname, 'PUBLIC') as grantee_name,
        coalesce(grantee.rolcanlogin, false) as grantee_can_login,
        case c.relkind when 'S' then 'sequence' else 'relation' end as object_kind,
        e.privilege_type,
        e.is_grantable
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    cross join lateral aclexplode(c.relacl) e
    left join pg_roles grantee on grantee.oid = e.grantee
    where c.relacl is not null
      and c.relkind in ('r', 'p', 'S', 'v', 'm', 'f')
      and e.grantee <> c.relowner
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
    union all
    select
        coalesce(grantee.rolname, 'PUBLIC'),
        coalesce(grantee.rolcanlogin, false),
        'function',
        e.privilege_type,
        e.is_grantable
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    cross join lateral aclexplode(p.proacl) e
    left join pg_roles grantee on grantee.oid = e.grantee
    where p.proacl is not null
      and e.grantee <> p.proowner
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
    union all
    select
        coalesce(grantee.rolname, 'PUBLIC'),
        coalesce(grantee.rolcanlogin, false),
        'schema',
        e.privilege_type,
        e.is_grantable
    from pg_namespace n
    cross join lateral aclexplode(n.nspacl) e
    left join pg_roles grantee on grantee.oid = e.grantee
    where n.nspacl is not null
      and e.grantee <> n.nspowner
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
)
select
    grantee_name,
    grantee_can_login,
    count(*) as explicit_privilege_count,
    count(*) filter (where object_kind = 'schema') as schema_privilege_count,
    count(*) filter (where object_kind = 'relation') as relation_privilege_count,
    count(*) filter (where object_kind = 'sequence') as sequence_privilege_count,
    count(*) filter (where object_kind = 'function') as function_privilege_count,
    count(*) filter (where is_grantable) as grant_option_count,
    string_agg(distinct privilege_type, ', ' order by privilege_type) as privilege_types,
    case when grantee_name = 'PUBLIC' or count(*) filter (where is_grantable) > 0 then 'medium' else 'unknown' end as risk_level,
    'Explicit privilege counts require comparison with the approved role and object baseline' as risk_reason
from explicit_grants
group by grantee_name, grantee_can_login
order by explicit_privilege_count desc, grantee_name
