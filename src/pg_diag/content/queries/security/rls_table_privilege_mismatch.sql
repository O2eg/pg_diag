with storage_table_roots_bounded as (
    select c.oid, c.relname, c.relowner, c.relacl, c.relforcerowsecurity, n.nspname
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where c.relkind = 'r'
      and c.relrowsecurity
      and greatest(coalesce(c.relpages, 0), 0) > 0
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
    order by c.relpages desc, n.nspname, c.relname, c.oid
    limit 10001
),
storage_table_roots as (
    select * from storage_table_roots_bounded limit 10000
),
storage_table_candidates as (
    select roots.*
    from storage_table_roots roots
    where not exists (
        select 1 from pg_depend d
        where d.classid = 'pg_class'::regclass
          and d.objid = roots.oid
          and d.deptype = 'e'
    )
),
partitioned_table_roots_bounded as (
    select c.oid, c.relname, c.relowner, c.relacl, c.relforcerowsecurity, n.nspname
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where c.relkind = 'p'
      and c.relrowsecurity
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
    order by n.nspname, c.relname, c.oid
    limit 10001
),
partitioned_table_roots as (
    select * from partitioned_table_roots_bounded limit 10000
),
partitioned_table_candidates as (
    select roots.*
    from partitioned_table_roots roots
    where not exists (
        select 1 from pg_depend d
        where d.classid = 'pg_class'::regclass
          and d.objid = roots.oid
          and d.deptype = 'e'
    )
),
table_candidates as (
    select * from storage_table_candidates
    union all
    select * from partitioned_table_candidates
),
expanded_acl_bounded as (
    select
        c.nspname::text as schema_name,
        c.relname::text as table_name,
        c.oid::int8 as table_oid,
        pg_catalog.pg_get_userbyid(c.relowner)::text as table_owner,
        coalesce(grantee.rolname::text, 'PUBLIC') as grantee_name,
        coalesce(grantee.rolcanlogin, false) as grantee_can_login,
        e.grantee as grantee_oid,
        e.privilege_type,
        e.is_grantable,
        c.relforcerowsecurity as force_rls
    from table_candidates c
    cross join lateral aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) e
    left join pg_roles grantee on grantee.oid = e.grantee
    where e.grantee <> c.relowner
      and (e.grantee = 0 or e.is_grantable or coalesce(grantee.rolcanlogin, false))
    limit 3001
),
expanded_acl as (
    select * from expanded_acl_bounded limit 3000
),
ranked_findings as (
    select *
    from expanded_acl
    order by schema_name, table_name, grantee_name, privilege_type
    limit 1001
),
coverage as (
    select
        (
            (select count(*) > 10000 from storage_table_roots_bounded)
            or (select count(*) > 10000 from partitioned_table_roots_bounded)
        ) as candidate_sample_truncated,
        (select count(*) > 3000 from expanded_acl_bounded) as acl_expansion_truncated,
        (select count(*) > 1000 from ranked_findings) as result_truncated
),
findings as (
    select * from ranked_findings limit 1000
)
select
    findings.schema_name,
    findings.table_name,
    findings.table_oid,
    findings.table_owner,
    findings.grantee_name,
    nullif(findings.grantee_oid, 0)::int8 as grantee_oid,
    findings.grantee_can_login,
    findings.privilege_type,
    findings.is_grantable,
    findings.force_rls,
    coverage.candidate_sample_truncated,
    coverage.acl_expansion_truncated,
    coverage.result_truncated,
    case when findings.grantee_oid = 0 or findings.is_grantable then 'medium' else 'unknown' end as risk_level,
    case
        when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
            then 'RLS privilege finding is part of a truncated bounded sample; review coverage flags before treating the inventory as complete'
        else 'Table privileges and RLS policies are independent layers; review PUBLIC or grantable access and compare direct grants with the baseline'
    end as risk_reason
from findings
cross join coverage
union all
select
    '[coverage]'::text,
    ''::text,
    null::int8,
    ''::text,
    ''::text,
    null::int8,
    false,
    ''::text,
    false,
    false,
    coverage.candidate_sample_truncated,
    coverage.acl_expansion_truncated,
    coverage.result_truncated,
    'unknown'::text,
    'The bounded RLS-table candidate, ACL expansion, or result sample was truncated; absence of findings is not a clean result'::text
from coverage
where coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
order by risk_level desc, schema_name, table_name, grantee_name, privilege_type
