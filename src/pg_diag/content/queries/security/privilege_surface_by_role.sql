with storage_relation_roots_bounded as (
    select c.oid, c.relkind, c.relowner, c.relacl, c.relname, n.nspname
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where c.relacl is not null
      and c.relkind in ('r', 'm')
      and greatest(coalesce(c.relpages, 0), 0) > 0
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
    order by c.relpages desc, n.nspname, c.relname, c.oid
    limit 10001
),
storage_relation_candidates as (
    select * from storage_relation_roots_bounded limit 10000
),
named_relation_roots_bounded as (
    select c.oid, c.relkind, c.relowner, c.relacl, c.relname, n.nspname
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where c.relacl is not null
      and c.relkind in ('p', 'S', 'v', 'f')
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
    order by n.nspname, c.relname, c.oid
    limit 10001
),
named_relation_candidates as (
    select * from named_relation_roots_bounded limit 10000
),
relation_candidates as (
    select * from storage_relation_candidates
    union all
    select * from named_relation_candidates
),
relation_grants_bounded as (
    select
        coalesce(grantee.rolname::text, 'PUBLIC') as grantee_name,
        coalesce(grantee.rolcanlogin, false) as grantee_can_login,
        case c.relkind when 'S' then 'sequence' else 'relation' end as object_kind,
        e.privilege_type,
        e.is_grantable
    from relation_candidates c
    cross join lateral aclexplode(c.relacl) e
    left join pg_roles grantee on grantee.oid = e.grantee
    where e.grantee <> c.relowner
    limit 1001
),
relation_grants as (
    select * from relation_grants_bounded limit 1000
),
function_roots_bounded as (
    select p.oid, p.proowner, p.proacl, p.proname, n.nspname
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    left join pg_stat_user_functions s on s.funcid = p.oid
    where p.proacl is not null
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
    order by coalesce(s.calls, 0) desc, n.nspname, p.proname, p.oid
    limit 1001
),
function_candidates as (
    select * from function_roots_bounded limit 1000
),
function_grants_bounded as (
    select
        coalesce(grantee.rolname::text, 'PUBLIC') as grantee_name,
        coalesce(grantee.rolcanlogin, false) as grantee_can_login,
        'function'::text as object_kind,
        e.privilege_type,
        e.is_grantable
    from function_candidates p
    cross join lateral aclexplode(p.proacl) e
    left join pg_roles grantee on grantee.oid = e.grantee
    where e.grantee <> p.proowner
    limit 1001
),
function_grants as (
    select * from function_grants_bounded limit 1000
),
schema_roots_bounded as (
    select n.oid, n.nspname, n.nspowner, n.nspacl
    from pg_namespace n
    where n.nspacl is not null
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
    order by n.nspname, n.oid
    limit 10001
),
schema_candidates as (
    select * from schema_roots_bounded limit 10000
),
schema_grants_bounded as (
    select
        coalesce(grantee.rolname::text, 'PUBLIC') as grantee_name,
        coalesce(grantee.rolcanlogin, false) as grantee_can_login,
        'schema'::text as object_kind,
        e.privilege_type,
        e.is_grantable
    from schema_candidates n
    cross join lateral aclexplode(n.nspacl) e
    left join pg_roles grantee on grantee.oid = e.grantee
    where e.grantee <> n.nspowner
    limit 1001
),
schema_grants as (
    select * from schema_grants_bounded limit 1000
),
explicit_grants as (
    select * from relation_grants
    union all
    select * from function_grants
    union all
    select * from schema_grants
),
ranked_findings as (
    select
        grantee_name,
        grantee_can_login,
        count(*) as sampled_explicit_privilege_count,
        count(*) filter (where object_kind = 'schema') as sampled_schema_privilege_count,
        count(*) filter (where object_kind = 'relation') as sampled_relation_privilege_count,
        count(*) filter (where object_kind = 'sequence') as sampled_sequence_privilege_count,
        count(*) filter (where object_kind = 'function') as sampled_function_privilege_count,
        count(*) filter (where is_grantable) as sampled_grant_option_count,
        string_agg(distinct privilege_type, ', ' order by privilege_type) as sampled_privilege_types
    from explicit_grants
    group by grantee_name, grantee_can_login
    order by sampled_explicit_privilege_count desc, grantee_name
    limit 1001
),
coverage as (
    select
        (
            (select count(*) > 10000 from storage_relation_roots_bounded)
            or (select count(*) > 10000 from named_relation_roots_bounded)
            or (select count(*) > 1000 from function_roots_bounded)
            or (select count(*) > 10000 from schema_roots_bounded)
        ) as candidate_sample_truncated,
        (
            (select count(*) > 1000 from relation_grants_bounded)
            or (select count(*) > 1000 from function_grants_bounded)
            or (select count(*) > 1000 from schema_grants_bounded)
        ) as acl_expansion_truncated,
        (select count(*) > 1000 from ranked_findings) as result_truncated
),
findings as (
    select * from ranked_findings limit 1000
)
select
    findings.grantee_name,
    findings.grantee_can_login,
    findings.sampled_explicit_privilege_count,
    findings.sampled_schema_privilege_count,
    findings.sampled_relation_privilege_count,
    findings.sampled_sequence_privilege_count,
    findings.sampled_function_privilege_count,
    findings.sampled_grant_option_count,
    findings.sampled_privilege_types,
    coverage.candidate_sample_truncated,
    coverage.acl_expansion_truncated,
    coverage.result_truncated,
    case when findings.grantee_name = 'PUBLIC' or findings.sampled_grant_option_count > 0 then 'medium' else 'unknown' end as risk_level,
    case
        when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
            then 'Sampled explicit privilege counts are partial; review coverage flags before comparing them with the approved baseline'
        else 'Sampled explicit privilege counts require comparison with the approved role and object baseline'
    end as risk_reason
from findings
cross join coverage
union all
select
    '[coverage]'::text,
    false,
    0::int8,
    0::int8,
    0::int8,
    0::int8,
    0::int8,
    0::int8,
    ''::text,
    coverage.candidate_sample_truncated,
    coverage.acl_expansion_truncated,
    coverage.result_truncated,
    'unknown'::text,
    'The bounded object candidate, ACL expansion, or role result sample was truncated; absence of findings is not a clean result'::text
from coverage
where coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
order by sampled_explicit_privilege_count desc, grantee_name
