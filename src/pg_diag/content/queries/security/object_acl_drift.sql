with storage_relation_roots_bounded as (
    select
        c.oid,
        c.relkind,
        c.relname,
        c.relowner,
        c.relacl,
        n.nspname
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where c.relkind in ('r', 'm')
      and greatest(coalesce(c.relpages, 0), 0) > 0
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
    order by c.relpages desc, n.nspname, c.relname, c.oid
    limit 10001
),
storage_relation_roots as (
    select *
    from storage_relation_roots_bounded
    limit 10000
),
storage_relation_candidates as (
    select roots.*
    from storage_relation_roots roots
    where not exists (
        select 1
        from pg_depend d
        where d.classid = 'pg_class'::regclass
          and d.objid = roots.oid
          and d.deptype = 'e'
    )
),
named_relation_roots_bounded as (
    select
        c.oid,
        c.relkind,
        c.relname,
        c.relowner,
        c.relacl,
        n.nspname
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where c.relkind in ('p', 'S', 'v', 'f')
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
    order by n.nspname, c.relname, c.oid
    limit 10001
),
named_relation_roots as (
    select *
    from named_relation_roots_bounded
    limit 10000
),
named_relation_candidates as (
    select roots.*
    from named_relation_roots roots
    where not exists (
        select 1
        from pg_depend d
        where d.classid = 'pg_class'::regclass
          and d.objid = roots.oid
          and d.deptype = 'e'
    )
),
function_roots_bounded as (
    select
        p.oid,
        p.proname,
        p.proowner,
        p.proacl,
        n.nspname
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    left join pg_stat_user_functions s on s.funcid = p.oid
    where n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
    order by coalesce(s.calls, 0) desc, n.nspname, p.proname, p.oid
    limit 1001
),
function_roots as (
    select *
    from function_roots_bounded
    limit 1000
),
function_candidates as (
    select roots.*
    from function_roots roots
    where not exists (
        select 1
        from pg_depend d
        where d.classid = 'pg_proc'::regclass
          and d.objid = roots.oid
          and d.deptype = 'e'
    )
),
acl_ready_objects as (
    select
        c.oid as object_oid,
        c.nspname as schema_name,
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
        1 as sample_priority,
        coalesce(
            c.relacl,
            acldefault(
                (case when c.relkind = 'S' then 'S' else 'r' end)::"char",
                c.relowner
            )
        ) as acl_items
    from storage_relation_candidates c
    union all
    select
        c.oid,
        c.nspname,
        case c.relkind
            when 'p' then 'partitioned_table'
            when 'S' then 'sequence'
            when 'v' then 'view'
            when 'f' then 'foreign_table'
            else c.relkind::text
        end,
        c.relname,
        2,
        coalesce(
            c.relacl,
            acldefault(
                (case when c.relkind = 'S' then 'S' else 'r' end)::"char",
                c.relowner
            )
        )
    from named_relation_candidates c
    union all
    select
        p.oid,
        p.nspname,
        'function',
        p.proname,
        3,
        coalesce(p.proacl, acldefault('f', p.proowner))
    from function_candidates p
),
ranked_acl_objects as (
    select
        objects.*,
        (
            coalesce(cardinality(objects.acl_items), 0)::int8
            * case
                when objects.object_kind = 'function' then 1
                when objects.object_kind = 'sequence' then 3
                else 8
              end
        ) as acl_expansion_budget,
        sum(
            coalesce(cardinality(objects.acl_items), 0)::int8
            * case
                when objects.object_kind = 'function' then 1
                when objects.object_kind = 'sequence' then 3
                else 8
              end
        ) over (
            partition by objects.sample_priority
            order by
                objects.schema_name,
                objects.object_kind,
                objects.object_name,
                objects.object_oid
        ) as cumulative_acl_expansion_budget
    from acl_ready_objects objects
),
bounded_acl_objects as (
    select *
    from ranked_acl_objects
    where cumulative_acl_expansion_budget <= case sample_priority
        when 1 then 1500
        when 2 then 1000
        else 500
    end
),
objects as (
    select
        p.schema_name,
        p.object_kind,
        p.object_name,
        normalized_acl.acl_signature
    from bounded_acl_objects p
    cross join lateral (
        select md5(
            coalesce(
                string_agg(
                    concat_ws(
                        ':',
                        acl.grantor::text,
                        acl.grantee::text,
                        acl.privilege_type,
                        acl.is_grantable::text
                    ),
                    ','
                    order by
                        acl.grantor,
                        acl.grantee,
                        acl.privilege_type,
                        acl.is_grantable
                ),
                ''
            )
        ) as acl_signature
        from aclexplode(p.acl_items) acl
    ) normalized_acl
),
candidate_coverage as (
    select
        (
            (select count(*) > 10000 from storage_relation_roots_bounded)
            or (select count(*) > 10000 from named_relation_roots_bounded)
            or (select count(*) > 1000 from function_roots_bounded)
        ) as candidate_sample_truncated
),
acl_coverage as (
    select
        coalesce(
            bool_or(
                cumulative_acl_expansion_budget > case sample_priority
                    when 1 then 1500
                    when 2 then 1000
                    else 500
                end
            ),
            false
        ) as acl_expansion_truncated
    from ranked_acl_objects
),
ranked_findings as (
    select
        schema_name,
        object_kind,
        count(*) as sampled_object_count,
        count(distinct acl_signature) as sampled_acl_signature_count,
        array_to_string((array_agg(object_name order by object_name))[1:10], ', ') as sample_objects
    from objects
    group by schema_name, object_kind
    having count(distinct acl_signature) > 1
    order by schema_name, object_kind
    limit 3001
),
result_coverage as (
    select count(*) > 3000 as result_truncated
    from ranked_findings
),
findings as (
    select *
    from ranked_findings
    limit 3000
)
select
    findings.schema_name,
    findings.object_kind,
    findings.sampled_object_count,
    findings.sampled_acl_signature_count,
    findings.sample_objects,
    coverage.candidate_sample_truncated,
    acl_coverage.acl_expansion_truncated,
    result_coverage.result_truncated,
    'unknown' as risk_level,
    case
        when coverage.candidate_sample_truncated
          or acl_coverage.acl_expansion_truncated
          or result_coverage.result_truncated
            then 'ACL drift was found, but one or more bounded samples were truncated; findings are partial'
        else 'Objects in the bounded sample of one schema and kind have different normalized ACL signatures; compare with the intended privilege baseline'
    end as risk_reason
from findings
cross join candidate_coverage coverage
cross join acl_coverage
cross join result_coverage
union all
select
    '[coverage]'::name as schema_name,
    'coverage'::text as object_kind,
    0::int8 as sampled_object_count,
    0::int8 as sampled_acl_signature_count,
    ''::text as sample_objects,
    coverage.candidate_sample_truncated,
    acl_coverage.acl_expansion_truncated,
    result_coverage.result_truncated,
    'unknown'::text as risk_level,
    'The bounded object, ACL expansion, or result sample was truncated; absence of ACL drift findings is not a clean result'::text as risk_reason
from candidate_coverage coverage
cross join acl_coverage
cross join result_coverage
where coverage.candidate_sample_truncated
   or acl_coverage.acl_expansion_truncated
   or result_coverage.result_truncated
order by schema_name, object_kind
