with user_schema_roots_bounded as (
    select
        n.oid as schema_oid,
        n.nspname as schema_name,
        n.nspowner,
        pg_catalog.pg_get_userbyid(n.nspowner)::text as schema_owner,
        n.nspacl
    from pg_namespace n
    where n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
    order by n.nspname, n.oid
    limit 10001
),
user_schemas as (
    select *
    from user_schema_roots_bounded
    limit 10000
),
expanded_schema_grants_bounded as (
    select
        s.schema_oid,
        coalesce(grantee.rolname::text, 'PUBLIC') as grantee_name,
        e.privilege_type,
        e.is_grantable
    from user_schemas s
    cross join lateral aclexplode(
        coalesce(s.nspacl, acldefault('n', s.nspowner))
    ) e
    left join pg_roles grantee on grantee.oid = e.grantee
    limit 3001
),
expanded_schema_grants as (
    select *
    from expanded_schema_grants_bounded
    limit 3000
),
schema_grants as (
    select
        schema_oid,
        grantee_name,
        bool_or(privilege_type = 'USAGE') as has_usage,
        bool_or(privilege_type = 'CREATE') as has_create,
        bool_or(is_grantable) as has_grant_option
    from expanded_schema_grants
    group by schema_oid, grantee_name
),
storage_object_roots_bounded as (
    select c.oid, c.relnamespace, c.relkind, c.relname
    from pg_class c
    join user_schemas s on s.schema_oid = c.relnamespace
    where c.relkind in ('r', 'm')
      and greatest(coalesce(c.relpages, 0), 0) > 0
    order by c.relpages desc, s.schema_name, c.relname, c.oid
    limit 10001
),
storage_object_candidates as (
    select * from storage_object_roots_bounded limit 10000
),
named_object_roots_bounded as (
    select c.oid, c.relnamespace, c.relkind, c.relname
    from pg_class c
    join user_schemas s on s.schema_oid = c.relnamespace
    where c.relkind in ('p', 'S', 'v', 'f')
    order by s.schema_name, c.relname, c.oid
    limit 10001
),
named_object_candidates as (
    select * from named_object_roots_bounded limit 10000
),
object_candidates as (
    select * from storage_object_candidates
    union all
    select * from named_object_candidates
),
object_counts as (
    select
        c.relnamespace as schema_oid,
        count(*) filter (where c.relkind in ('r', 'p')) as sampled_table_count,
        count(*) filter (where c.relkind = 'S') as sampled_sequence_count,
        count(*) filter (where c.relkind in ('v', 'm')) as sampled_view_count
    from object_candidates c
    group by c.relnamespace
),
function_roots_bounded as (
    select p.oid, p.pronamespace, p.proname
    from pg_proc p
    join user_schemas u on u.schema_oid = p.pronamespace
    left join pg_stat_user_functions s on s.funcid = p.oid
    order by coalesce(s.calls, 0) desc, u.schema_name, p.proname, p.oid
    limit 1001
),
function_candidates as (
    select * from function_roots_bounded limit 1000
),
function_counts as (
    select
        p.pronamespace as schema_oid,
        count(*) as sampled_function_count
    from function_candidates p
    group by p.pronamespace
),
ranked_findings as (
    select
        s.schema_name::text as schema_name,
        s.schema_owner,
        g.grantee_name,
        g.has_usage,
        g.has_create,
        g.has_grant_option,
        coalesce(o.sampled_table_count, 0) as sampled_table_count,
        coalesce(o.sampled_sequence_count, 0) as sampled_sequence_count,
        coalesce(o.sampled_view_count, 0) as sampled_view_count,
        coalesce(f.sampled_function_count, 0) as sampled_function_count
    from user_schemas s
    join schema_grants g on g.schema_oid = s.schema_oid
    left join object_counts o on o.schema_oid = s.schema_oid
    left join function_counts f on f.schema_oid = s.schema_oid
    order by s.schema_name, g.grantee_name
    limit 1001
),
coverage as (
    select
        (
            (select count(*) > 10000 from user_schema_roots_bounded)
            or (select count(*) > 10000 from storage_object_roots_bounded)
            or (select count(*) > 10000 from named_object_roots_bounded)
            or (select count(*) > 1000 from function_roots_bounded)
        ) as candidate_sample_truncated,
        (select count(*) > 3000 from expanded_schema_grants_bounded) as acl_expansion_truncated,
        (select count(*) > 1000 from ranked_findings) as result_truncated
),
findings as (
    select * from ranked_findings limit 1000
)
select
    findings.schema_name,
    findings.schema_owner,
    findings.grantee_name,
    findings.has_usage,
    findings.has_create,
    findings.has_grant_option,
    findings.sampled_table_count,
    findings.sampled_sequence_count,
    findings.sampled_view_count,
    findings.sampled_function_count,
    coverage.candidate_sample_truncated,
    coverage.acl_expansion_truncated,
    coverage.result_truncated,
    case
        when findings.grantee_name = 'PUBLIC' and findings.has_create then 'high'
        when findings.grantee_name = 'PUBLIC' or findings.has_grant_option then 'medium'
        else 'ok'
    end as risk_level,
    case
        when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
            then 'Schema privilege row is part of a truncated bounded sample; review coverage flags before treating the matrix as complete'
        when findings.grantee_name = 'PUBLIC' and findings.has_create then 'PUBLIC can create objects in this schema'
        when findings.grantee_name = 'PUBLIC' then 'PUBLIC has schema privileges'
        when findings.has_grant_option then 'Schema privilege can be re-granted'
        else 'Schema privilege row'
    end as risk_reason
from findings
cross join coverage
union all
select
    '[coverage]'::text,
    ''::text,
    ''::text,
    false,
    false,
    false,
    0::int8,
    0::int8,
    0::int8,
    0::int8,
    coverage.candidate_sample_truncated,
    coverage.acl_expansion_truncated,
    coverage.result_truncated,
    'unknown'::text,
    'The bounded schema, object, function, ACL expansion, or matrix result sample was truncated; absence of findings is not a clean result'::text
from coverage
where coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
order by risk_level desc, schema_name, grantee_name
