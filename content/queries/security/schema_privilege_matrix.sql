with user_schemas as (
    select
        n.oid as schema_oid,
        n.nspname as schema_name,
        pg_catalog.pg_get_userbyid(n.nspowner) as schema_owner,
        n.nspacl
    from pg_namespace n
    where n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
),
schema_grants as (
    select
        s.schema_oid,
        coalesce(grantee.rolname, 'PUBLIC') as grantee_name,
        bool_or(e.privilege_type = 'USAGE') as has_usage,
        bool_or(e.privilege_type = 'CREATE') as has_create,
        bool_or(e.is_grantable) as has_grant_option
    from user_schemas s
    cross join lateral aclexplode(coalesce(s.nspacl, acldefault('n', (select nspowner from pg_namespace where oid = s.schema_oid)))) e
    left join pg_roles grantee on grantee.oid = e.grantee
    group by s.schema_oid, coalesce(grantee.rolname, 'PUBLIC')
),
object_counts as (
    select
        n.oid as schema_oid,
        count(*) filter (where c.relkind in ('r', 'p')) as table_count,
        count(*) filter (where c.relkind = 'S') as sequence_count,
        count(*) filter (where c.relkind in ('v', 'm')) as view_count
    from pg_namespace n
    left join pg_class c on c.relnamespace = n.oid
    group by n.oid
),
function_counts as (
    select
        n.oid as schema_oid,
        count(p.oid) as function_count
    from pg_namespace n
    left join pg_proc p on p.pronamespace = n.oid
    group by n.oid
)
select
    s.schema_name,
    s.schema_owner,
    g.grantee_name,
    g.has_usage,
    g.has_create,
    g.has_grant_option,
    coalesce(o.table_count, 0) as table_count,
    coalesce(o.sequence_count, 0) as sequence_count,
    coalesce(o.view_count, 0) as view_count,
    coalesce(f.function_count, 0) as function_count,
    case
        when g.grantee_name = 'PUBLIC' and g.has_create then 'high'
        when g.grantee_name = 'PUBLIC' or g.has_grant_option then 'medium'
        else 'ok'
    end as risk_level,
    case
        when g.grantee_name = 'PUBLIC' and g.has_create then 'PUBLIC can create objects in this schema'
        when g.grantee_name = 'PUBLIC' then 'PUBLIC has schema privileges'
        when g.has_grant_option then 'Schema privilege can be re-granted'
        else 'Schema privilege row'
    end as risk_reason
from user_schemas s
join schema_grants g on g.schema_oid = s.schema_oid
left join object_counts o on o.schema_oid = s.schema_oid
left join function_counts f on f.schema_oid = s.schema_oid
order by risk_level desc, s.schema_name, g.grantee_name
