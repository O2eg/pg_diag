with relation_objects as (
    select
        case c.relkind
            when 'r' then 'table'
            when 'p' then 'partitioned_table'
            when 'S' then 'sequence'
            when 'v' then 'view'
            when 'm' then 'materialized_view'
            when 'f' then 'foreign_table'
            else c.relkind::text
        end as object_kind,
        n.nspname as schema_name,
        c.relname as object_name,
        pg_catalog.pg_get_userbyid(c.relowner) as owner_name,
        r.rolsuper as owner_is_superuser
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    join pg_roles r on r.oid = c.relowner
    where c.relkind in ('r', 'p', 'S', 'v', 'm', 'f')
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
      and not exists (
          select 1
          from pg_depend d
          where d.classid = 'pg_class'::regclass
            and d.objid = c.oid
            and d.deptype = 'e'
      )
),
function_objects as (
    select
        'function' as object_kind,
        n.nspname as schema_name,
        p.proname as object_name,
        pg_catalog.pg_get_userbyid(p.proowner) as owner_name,
        r.rolsuper as owner_is_superuser
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    join pg_roles r on r.oid = p.proowner
    where n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
      and not exists (
          select 1
          from pg_depend d
          where d.classid = 'pg_proc'::regclass
            and d.objid = p.oid
            and d.deptype = 'e'
      )
)
select
    object_kind,
    schema_name,
    object_name,
    owner_name,
    owner_is_superuser,
    'high' as risk_level,
    'User object is owned by a PostgreSQL superuser' as risk_reason
from (
    select * from relation_objects
    union all
    select * from function_objects
) objects
where owner_is_superuser
order by schema_name, object_kind, object_name
