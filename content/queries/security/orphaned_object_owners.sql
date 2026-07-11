with object_owners as (
    select
        pg_catalog.pg_get_userbyid(c.relowner) as owner_name,
        c.relowner as owner_oid,
        count(*) as object_count
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where c.relkind in ('r', 'p', 'S', 'v', 'm', 'f')
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
      and not exists (
          select 1 from pg_depend d
          where d.classid = 'pg_class'::regclass and d.objid = c.oid and d.deptype = 'e'
      )
    group by c.relowner
    union all
    select
        pg_catalog.pg_get_userbyid(p.proowner),
        p.proowner,
        count(*)
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
      and not exists (
          select 1 from pg_depend d
          where d.classid = 'pg_proc'::regclass and d.objid = p.oid and d.deptype = 'e'
      )
    group by p.proowner
),
owners as (
    select owner_name, owner_oid, sum(object_count) as object_count
    from object_owners
    group by owner_name, owner_oid
)
select
    owners.owner_name,
    roles.rolcanlogin as owner_can_login,
    roles.rolsuper as owner_is_superuser,
    owners.object_count,
    'unknown' as risk_level,
    'No-login ownership is a recommended privilege-separation pattern; verify the role against the ownership baseline' as risk_reason
from owners
join pg_roles roles on roles.oid = owners.owner_oid
where not roles.rolcanlogin
  and owners.owner_name not like 'pg_%'
  and owners.owner_name not in ('postgres', 'pg_database_owner')
order by owners.object_count desc, owners.owner_name
