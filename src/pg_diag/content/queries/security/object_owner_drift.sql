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
objects as (
    select
        n.nspname::text as schema_name,
        case c.relkind
            when 'r' then 'table'
            when 'p' then 'partitioned_table'
            when 'S' then 'sequence'
            when 'v' then 'view'
            when 'm' then 'materialized_view'
            when 'f' then 'foreign_table'
            else c.relkind::text
        end as object_kind,
        c.relname::text as object_name,
        pg_catalog.pg_get_userbyid(c.relowner)::text as owner_name,
        r.rolsuper as owner_is_superuser
    from relation_candidates candidates
    join pg_class c on c.oid = candidates.oid
    join pg_namespace n on n.oid = c.relnamespace
    join pg_roles r on r.oid = c.relowner
    union all
    select
        n.nspname::text,
        'function'::text,
        p.proname::text,
        pg_catalog.pg_get_userbyid(p.proowner)::text,
        r.rolsuper
    from function_candidates candidates
    join pg_proc p on p.oid = candidates.oid
    join pg_namespace n on n.oid = p.pronamespace
    join pg_roles r on r.oid = p.proowner
),
ranked_findings as (
    select
        schema_name,
        object_kind,
        count(*) as sampled_object_count,
        count(distinct owner_name) as sampled_owner_count,
        string_agg(distinct owner_name, ', ' order by owner_name) as owners,
        count(*) filter (where owner_is_superuser) as sampled_superuser_owned_count
    from objects
    group by schema_name, object_kind
    having count(distinct owner_name) > 1
    order by schema_name, object_kind
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
    findings.schema_name,
    findings.object_kind,
    findings.sampled_object_count,
    findings.sampled_owner_count,
    findings.owners,
    findings.sampled_superuser_owned_count,
    coverage.candidate_sample_truncated,
    coverage.result_truncated,
    'unknown' as risk_level,
    case
        when coverage.candidate_sample_truncated or coverage.result_truncated
            then 'Owner drift was found in a truncated bounded sample; review coverage flags before treating the inventory as complete'
        else 'Objects in the bounded candidate sample have mixed owners; compare with the intended ownership baseline'
    end as risk_reason
from findings
cross join coverage
union all
select
    '[coverage]'::text,
    'coverage'::text,
    0::int8,
    0::int8,
    ''::text,
    0::int8,
    coverage.candidate_sample_truncated,
    coverage.result_truncated,
    'unknown'::text,
    'The bounded object candidate or result sample was truncated; objects outside the root may be missed, including when selected roots are later excluded as extension-owned'::text
from coverage
where coverage.candidate_sample_truncated or coverage.result_truncated
order by risk_level desc, schema_name, object_kind
