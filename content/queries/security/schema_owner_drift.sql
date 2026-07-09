with objects as (
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
        pg_catalog.pg_get_userbyid(c.relowner) as object_owner,
        pg_catalog.pg_get_userbyid(n.nspowner) as schema_owner
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where c.relkind in ('r', 'p', 'S', 'v', 'm', 'f')
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
        pg_catalog.pg_get_userbyid(n.nspowner)
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
      and not exists (
          select 1 from pg_depend d
          where d.classid = 'pg_proc'::regclass and d.objid = p.oid and d.deptype = 'e'
      )
)
select
    object_kind,
    schema_name,
    object_name,
    object_owner,
    schema_owner,
    'medium' as risk_level,
    'Object owner differs from the containing schema owner' as risk_reason
from objects
where object_owner <> schema_owner
order by schema_name, object_kind, object_name
