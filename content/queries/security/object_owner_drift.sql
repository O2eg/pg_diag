with objects as (
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
        pg_catalog.pg_get_userbyid(c.relowner) as owner_name,
        r.rolsuper as owner_is_superuser
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    join pg_roles r on r.oid = c.relowner
    where c.relkind in ('r', 'p', 'S', 'v', 'm', 'f')
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
      and not exists (
          select 1 from pg_depend d
          where d.classid = 'pg_class'::regclass and d.objid = c.oid and d.deptype = 'e'
      )
    union all
    select
        n.nspname,
        'function',
        p.proname,
        pg_catalog.pg_get_userbyid(p.proowner),
        r.rolsuper
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    join pg_roles r on r.oid = p.proowner
    where n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
      and not exists (
          select 1 from pg_depend d
          where d.classid = 'pg_proc'::regclass and d.objid = p.oid and d.deptype = 'e'
      )
)
select
    schema_name,
    object_kind,
    count(*) as object_count,
    count(distinct owner_name) as owner_count,
    string_agg(distinct owner_name, ', ' order by owner_name) as owners,
    count(*) filter (where owner_is_superuser) as superuser_owned_count,
    case when bool_or(owner_is_superuser) then 'high' else 'medium' end as risk_level,
    'Objects of the same kind in one schema have mixed owners' as risk_reason
from objects
group by schema_name, object_kind
having count(distinct owner_name) > 1
order by risk_level desc, schema_name, object_kind
