with storage_relation_roots_bounded as (
    select c.oid, c.relkind, c.relname, c.relowner, c.relacl, n.nspname
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
storage_relation_roots as (
    select * from storage_relation_roots_bounded limit 10000
),
storage_relation_candidates as (
    select roots.*
    from storage_relation_roots roots
    where not exists (
        select 1 from pg_depend d
        where d.classid = 'pg_class'::regclass
          and d.objid = roots.oid
          and d.deptype = 'e'
    )
),
named_relation_roots_bounded as (
    select c.oid, c.relkind, c.relname, c.relowner, c.relacl, n.nspname
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where c.relacl is not null
      and c.relkind in ('p', 'S', 'v', 'f')
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
    order by n.nspname, c.relname, c.oid
    limit 10001
),
named_relation_roots as (
    select * from named_relation_roots_bounded limit 10000
),
named_relation_candidates as (
    select roots.*
    from named_relation_roots roots
    where not exists (
        select 1 from pg_depend d
        where d.classid = 'pg_class'::regclass
          and d.objid = roots.oid
          and d.deptype = 'e'
    )
),
relation_candidates as (
    select * from storage_relation_candidates
    union all
    select * from named_relation_candidates
),
relation_grants_bounded as (
    select
        case c.relkind when 'S' then 'sequence' else 'relation' end as object_kind,
        c.nspname::text as schema_name,
        c.relname::text as object_name,
        pg_catalog.pg_get_userbyid(c.relowner)::text as owner_name,
        coalesce(grantee.rolname::text, 'PUBLIC') as grantee_name,
        coalesce(grantee.rolcanlogin, false) as grantee_can_login,
        e.privilege_type
    from relation_candidates c
    cross join lateral aclexplode(c.relacl) e
    left join pg_roles grantee on grantee.oid = e.grantee
    where e.is_grantable
      and e.grantee <> c.relowner
    limit 1001
),
relation_grants as (
    select * from relation_grants_bounded limit 1000
),
function_roots_bounded as (
    select p.oid, p.proname, p.proowner, p.proacl, n.nspname
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    left join pg_stat_user_functions s on s.funcid = p.oid
    where p.proacl is not null
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
    order by coalesce(s.calls, 0) desc, n.nspname, p.proname, p.oid
    limit 1001
),
function_roots as (
    select * from function_roots_bounded limit 1000
),
function_candidates as (
    select roots.*
    from function_roots roots
    where not exists (
        select 1 from pg_depend d
        where d.classid = 'pg_proc'::regclass
          and d.objid = roots.oid
          and d.deptype = 'e'
    )
),
function_grants_bounded as (
    select
        'function'::text as object_kind,
        p.nspname::text as schema_name,
        p.proname::text as object_name,
        pg_catalog.pg_get_userbyid(p.proowner)::text as owner_name,
        coalesce(grantee.rolname::text, 'PUBLIC') as grantee_name,
        coalesce(grantee.rolcanlogin, false) as grantee_can_login,
        e.privilege_type
    from function_candidates p
    cross join lateral aclexplode(p.proacl) e
    left join pg_roles grantee on grantee.oid = e.grantee
    where e.is_grantable
      and e.grantee <> p.proowner
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
        'schema'::text as object_kind,
        n.nspname::text as schema_name,
        n.nspname::text as object_name,
        pg_catalog.pg_get_userbyid(n.nspowner)::text as owner_name,
        coalesce(grantee.rolname::text, 'PUBLIC') as grantee_name,
        coalesce(grantee.rolcanlogin, false) as grantee_can_login,
        e.privilege_type
    from schema_candidates n
    cross join lateral aclexplode(n.nspacl) e
    left join pg_roles grantee on grantee.oid = e.grantee
    where e.is_grantable
      and e.grantee <> n.nspowner
    limit 1001
),
schema_grants as (
    select * from schema_grants_bounded limit 1000
),
grants as (
    select * from relation_grants
    union all
    select * from function_grants
    union all
    select * from schema_grants
),
ranked_findings as (
    select *
    from grants
    order by schema_name, object_kind, object_name, grantee_name, privilege_type
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
    findings.object_kind,
    findings.schema_name,
    findings.object_name,
    findings.owner_name,
    findings.grantee_name,
    findings.grantee_can_login,
    findings.privilege_type,
    coverage.candidate_sample_truncated,
    coverage.acl_expansion_truncated,
    coverage.result_truncated,
    'medium' as risk_level,
    case
        when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
            then 'Grant-option finding is part of a truncated bounded sample; review coverage flags before treating the inventory as complete'
        else 'Non-owner role can re-grant privileges WITH GRANT OPTION in the bounded object sample'
    end as risk_reason
from findings
cross join coverage
union all
select
    'coverage'::text,
    '[coverage]'::text,
    ''::text,
    ''::text,
    ''::text,
    false,
    ''::text,
    coverage.candidate_sample_truncated,
    coverage.acl_expansion_truncated,
    coverage.result_truncated,
    'unknown'::text,
    'The bounded object candidate, ACL expansion, or result sample was truncated; absence of grant-option findings is not a clean result'::text
from coverage
where coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
order by schema_name, object_kind, object_name, grantee_name, privilege_type
