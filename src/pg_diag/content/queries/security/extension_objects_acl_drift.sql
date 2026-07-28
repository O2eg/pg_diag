with extension_relations_bounded as (
    select
        e.extname::text as extension_name,
        'relation'::text as object_kind,
        n.nspname::text as schema_name,
        c.relname::text as object_name,
        c.relacl::text as acl_text
    from pg_extension e
    join pg_depend d on d.refclassid = 'pg_extension'::regclass and d.refobjid = e.oid and d.deptype = 'e'
    join pg_class c on d.classid = 'pg_class'::regclass and d.objid = c.oid
    join pg_namespace n on n.oid = c.relnamespace
    where c.relacl is not null
    order by greatest(coalesce(c.relpages, 0), 0) desc,
             e.extname, n.nspname, c.relname, c.oid
    limit 2001
),
extension_relations as (
    select *
    from extension_relations_bounded
    limit 2000
),
extension_functions_bounded as (
    select
        e.extname::text as extension_name,
        'function'::text as object_kind,
        n.nspname::text as schema_name,
        p.proname::text as object_name,
        p.proacl::text as acl_text
    from pg_extension e
    join pg_depend d on d.refclassid = 'pg_extension'::regclass and d.refobjid = e.oid and d.deptype = 'e'
    join pg_proc p on d.classid = 'pg_proc'::regclass and d.objid = p.oid
    join pg_namespace n on n.oid = p.pronamespace
    left join pg_stat_user_functions stats on stats.funcid = p.oid
    where p.proacl is not null
    order by coalesce(stats.calls, 0) desc,
             e.extname, n.nspname, p.proname, p.oid
    limit 1001
),
extension_functions as (
    select *
    from extension_functions_bounded
    limit 1000
),
bounded_objects as (
    select * from extension_relations
    union all
    select * from extension_functions
),
ranked_findings as (
    select *
    from bounded_objects
    order by extension_name, schema_name, object_kind, object_name
    limit 1001
),
coverage as (
    select
        (select count(*) > 2000 from extension_relations_bounded) as relation_candidates_truncated,
        (select count(*) > 1000 from extension_functions_bounded) as function_candidates_truncated,
        (select count(*) > 1000 from ranked_findings) as result_truncated
),
findings as (
    select *
    from ranked_findings
    limit 1000
)
select
    findings.extension_name,
    findings.object_kind,
    findings.schema_name,
    findings.object_name,
    findings.acl_text,
    coverage.relation_candidates_truncated,
    coverage.function_candidates_truncated,
    coverage.result_truncated,
    'unknown' as risk_level,
    case
        when coverage.relation_candidates_truncated
          or coverage.function_candidates_truncated
          or coverage.result_truncated
            then 'Extension-owned object with an explicit ACL was found in a truncated bounded sample; review coverage flags before treating the inventory as complete'
        else 'Extension-owned object has an explicit ACL entry; compare it with the extension and privilege baselines'
    end as risk_reason
from findings
cross join coverage
union all
select
    '[coverage]'::text,
    'coverage'::text,
    ''::text,
    ''::text,
    ''::text,
    coverage.relation_candidates_truncated,
    coverage.function_candidates_truncated,
    coverage.result_truncated,
    'unknown'::text,
    'The bounded extension relation, function, or result sample was truncated; absence of ACL drift findings is not a clean result'::text
from coverage
where coverage.relation_candidates_truncated
   or coverage.function_candidates_truncated
   or coverage.result_truncated
order by extension_name, schema_name, object_kind, object_name
