with storage_relation_roots_bounded as (
  select c.oid, c.relname, c.relowner, c.relacl, n.nspname
  from pg_catalog.pg_class c
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where c.relkind = 'r'
    and greatest(coalesce(c.relpages, 0), 0) > 0
    and n.nspname not in ('pg_catalog', 'information_schema', 'pg_toast')
    and n.nspname not like 'pg_temp_%'
    and n.nspname not like 'pg_toast_temp_%'
  order by c.relpages desc, n.nspname, c.relname, c.oid
  limit 10001
),
storage_relation_candidates as (
  select *
  from storage_relation_roots_bounded
  limit 10000
),
named_relation_roots_bounded as (
  select c.oid, c.relname, c.relowner, c.relacl, n.nspname
  from pg_catalog.pg_class c
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where c.relkind in ('p', 'v', 'f')
    and n.nspname not in ('pg_catalog', 'information_schema', 'pg_toast')
    and n.nspname not like 'pg_temp_%'
    and n.nspname not like 'pg_toast_temp_%'
  order by n.nspname, c.relname, c.oid
  limit 10001
),
named_relation_candidates as (
  select *
  from named_relation_roots_bounded
  limit 10000
),
relation_candidates as (
  select * from storage_relation_candidates
  union all
  select * from named_relation_candidates
),
expanded_acl_bounded as (
  select
    c.oid as relation_oid,
    case when acl.grantee = 0 then 'PUBLIC' else pg_catalog.pg_get_userbyid(acl.grantee)::text end as grantee,
    c.nspname::text as table_schema,
    c.relname::text as table_name,
    acl.privilege_type,
    acl.is_grantable,
    coalesce(grantee_role.rolsuper, false) as grantee_is_superuser,
    pg_catalog.pg_get_userbyid(c.relowner)::text as table_owner
  from relation_candidates c
  cross join lateral pg_catalog.aclexplode(
    coalesce(c.relacl, pg_catalog.acldefault('r', c.relowner))
  ) acl
  left join pg_catalog.pg_roles grantee_role on grantee_role.oid = acl.grantee
  where acl.privilege_type in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')
    and (
      acl.grantee = 0
      or (acl.is_grantable and acl.grantee <> c.relowner)
    )
  limit 3001
),
expanded_acl as (
  select *
  from expanded_acl_bounded
  limit 3000
),
ranked_findings as (
  select *
  from expanded_acl
  order by table_schema, table_name, grantee, privilege_type, relation_oid
  limit 1001
),
coverage as (
  select
    (
      (select count(*) > 10000 from storage_relation_roots_bounded)
      or (select count(*) > 10000 from named_relation_roots_bounded)
    ) as candidate_sample_truncated,
    (select count(*) > 3000 from expanded_acl_bounded) as acl_expansion_truncated,
    (select count(*) > 1000 from ranked_findings) as result_truncated
),
findings as (
  select *
  from ranked_findings
  limit 1000
)
select
  findings.relation_oid,
  findings.grantee,
  findings.table_schema,
  findings.table_name,
  findings.privilege_type,
  findings.is_grantable,
  findings.grantee_is_superuser,
  findings.table_owner,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  coverage.result_truncated,
  case
    when findings.grantee = 'PUBLIC' and findings.privilege_type in ('DELETE', 'TRUNCATE', 'UPDATE') then 'high'
    when findings.grantee = 'PUBLIC' then 'medium'
    when findings.is_grantable then 'medium'
    else 'ok'
  end as risk_level,
  case
    when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
      then 'DML privilege finding is part of a truncated bounded sample; review coverage flags before treating the inventory as complete'
    when findings.grantee = 'PUBLIC' then 'DML privilege is granted to PUBLIC'
    when findings.is_grantable then 'DML privilege can be granted onward'
    else 'informational DML privilege'
  end as risk_reason
from findings
cross join coverage
union all
select
  null::oid,
  '[coverage]'::text,
  ''::text,
  ''::text,
  ''::text,
  false,
  false,
  ''::text,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  coverage.result_truncated,
  'unknown'::text,
  'The bounded relation candidate, ACL expansion, or result sample was truncated; absence of findings is not a clean result'::text
from coverage
where coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
order by risk_level desc, table_schema, table_name, grantee, privilege_type, relation_oid
