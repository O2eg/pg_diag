with db_owner as (
    select pg_catalog.pg_get_userbyid(datdba) as database_owner
    from pg_database
    where datname = current_database()
),
objects as (
    select
        'schema' as object_kind,
        n.nspname as schema_name,
        n.nspname as object_name,
        pg_catalog.pg_get_userbyid(n.nspowner) as owner_name
    from pg_namespace n
    where n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
    union all
    select
        case c.relkind
            when 'r' then 'table'
            when 'p' then 'partitioned_table'
            when 'S' then 'sequence'
            when 'v' then 'view'
            when 'm' then 'materialized_view'
            when 'f' then 'foreign_table'
            else c.relkind::text
        end,
        n.nspname,
        c.relname,
        pg_catalog.pg_get_userbyid(c.relowner)
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
        pg_catalog.pg_get_userbyid(p.proowner)
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
    objects.object_kind,
    objects.schema_name,
    objects.object_name,
    objects.owner_name,
    db_owner.database_owner,
    'medium' as risk_level,
    'Database object is not owned by the database owner role' as risk_reason
from objects
cross join db_owner
where objects.owner_name <> db_owner.database_owner
order by objects.schema_name, objects.object_kind, objects.object_name
