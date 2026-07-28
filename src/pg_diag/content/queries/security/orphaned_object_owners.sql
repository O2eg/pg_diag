with stored_relation_roots_bounded as (
    select c.oid
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where c.relkind in ('r', 'm')
      and greatest(coalesce(c.relpages, 0), 0) > 0
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
    order by c.relpages desc, n.nspname, c.relname, c.oid
    limit 10001
),
stored_relation_roots as (
    select * from stored_relation_roots_bounded limit 10000
),
named_relation_roots_bounded as (
    select c.oid
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where c.relkind in ('p', 'S', 'v', 'f')
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
    order by n.nspname, c.relname, c.oid
    limit 10001
),
named_relation_roots as (
    select * from named_relation_roots_bounded limit 10000
),
relation_roots as (
    select oid from stored_relation_roots
    union all
    select oid from named_relation_roots
),
relation_candidates as (
    select roots.oid
    from relation_roots roots
    where not exists (
        select 1 from pg_depend d
        where d.classid = 'pg_class'::regclass
          and d.objid = roots.oid
          and d.deptype = 'e'
    )
),
function_roots_bounded as (
    select p.oid
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    left join pg_stat_user_functions stats on stats.funcid = p.oid
    where n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
    order by coalesce(stats.calls, 0) desc, n.nspname, p.proname, p.oid
    limit 1001
),
function_roots as (
    select * from function_roots_bounded limit 1000
),
function_candidates as (
    select roots.oid
    from function_roots roots
    where not exists (
        select 1 from pg_depend d
        where d.classid = 'pg_proc'::regclass
          and d.objid = roots.oid
          and d.deptype = 'e'
    )
),
object_owners as (
    select
        pg_catalog.pg_get_userbyid(c.relowner)::text as owner_name,
        c.relowner as owner_oid,
        count(*) as object_count
    from relation_candidates candidates
    join pg_class c on c.oid = candidates.oid
    group by c.relowner
    union all
    select
        pg_catalog.pg_get_userbyid(p.proowner)::text,
        p.proowner,
        count(*)
    from function_candidates candidates
    join pg_proc p on p.oid = candidates.oid
    group by p.proowner
),
owners as (
    select owner_name, owner_oid, sum(object_count)::int8 as object_count
    from object_owners
    group by owner_name, owner_oid
),
ranked_findings as (
    select
        owners.owner_name,
        roles.rolcanlogin as owner_can_login,
        roles.rolsuper as owner_is_superuser,
        owners.object_count as sampled_object_count
    from owners
    join pg_roles roles on roles.oid = owners.owner_oid
    where not roles.rolcanlogin
      and owners.owner_name not like 'pg_%'
      and owners.owner_name not in ('postgres', 'pg_database_owner')
    order by owners.object_count desc, owners.owner_name
    limit 1001
),
coverage as (
    select
        (
            (select count(*) > 10000 from stored_relation_roots_bounded)
            or (select count(*) > 10000 from named_relation_roots_bounded)
            or (select count(*) > 1000 from function_roots_bounded)
        ) as candidate_sample_truncated,
        (select count(*) > 1000 from ranked_findings) as result_truncated
),
findings as (
    select * from ranked_findings limit 1000
)
select
    findings.owner_name,
    findings.owner_can_login,
    findings.owner_is_superuser,
    findings.sampled_object_count,
    coverage.candidate_sample_truncated,
    coverage.result_truncated,
    'unknown' as risk_level,
    case
        when coverage.candidate_sample_truncated or coverage.result_truncated
            then 'No-login ownership was found in a truncated bounded sample; review coverage flags before treating the inventory as complete'
        else 'No-login ownership in the bounded candidate sample should be verified against the ownership baseline'
    end as risk_reason
from findings
cross join coverage
union all
select
    '[coverage]'::text,
    false,
    false,
    0::int8,
    coverage.candidate_sample_truncated,
    coverage.result_truncated,
    'unknown'::text,
    'The bounded object candidate or result sample was truncated; objects outside the root may be missed, including when selected roots are later excluded as extension-owned'::text
from coverage
where coverage.candidate_sample_truncated or coverage.result_truncated
order by sampled_object_count desc, owner_name
