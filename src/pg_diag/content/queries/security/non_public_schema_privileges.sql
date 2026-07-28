with schema_roots_bounded as (
  select
    n.oid,
    n.nspname,
    n.nspowner,
    n.nspacl
  from pg_catalog.pg_namespace n
  where n.nspname <> 'public'
    and n.nspname not in ('pg_catalog', 'information_schema', 'pg_toast')
    and n.nspname not like 'pg_%'
    and n.nspname not like 'pg_temp_%'
    and n.nspname not like 'pg_toast_temp_%'
  order by n.nspname, n.oid
  limit 10001
),
schema_candidates as (
  select *
  from schema_roots_bounded
  limit 10000
),
expanded_acl_bounded as (
  select
    n.oid,
    n.nspname::text as nspname,
    n.nspowner,
    acl.grantor,
    acl.grantee,
    acl.privilege_type,
    acl.is_grantable
  from schema_candidates n
  cross join lateral pg_catalog.aclexplode(
    coalesce(n.nspacl, pg_catalog.acldefault('n', n.nspowner))
  ) as acl
  where acl.grantee = 0
     or (acl.privilege_type = 'CREATE' and acl.grantee <> n.nspowner)
     or (acl.is_grantable and acl.grantee <> n.nspowner)
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
  order by nspname, grantee, privilege_type
  limit 1001
),
coverage as (
  select
    (select count(*) > 10000 from schema_roots_bounded) as candidate_sample_truncated,
    (select count(*) > 3000 from expanded_acl_bounded) as acl_expansion_truncated,
    (select count(*) > 1000 from ranked_findings) as result_truncated
),
findings as (
  select *
  from ranked_findings
  limit 1000
)
select
  findings.nspname as schema_name,
  pg_catalog.pg_get_userbyid(findings.nspowner)::text as schema_owner,
  case when findings.grantee = 0 then 'PUBLIC' else pg_catalog.pg_get_userbyid(findings.grantee)::text end as grantee,
  pg_catalog.pg_get_userbyid(findings.grantor)::text as grantor,
  findings.privilege_type,
  findings.is_grantable,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  coverage.result_truncated,
  case
    when findings.grantee = 0 and findings.privilege_type = 'CREATE' then 'high'
    when findings.grantee = 0 then 'unknown'
    when findings.privilege_type = 'CREATE' then 'medium'
    when findings.is_grantable then 'medium'
    else 'ok'
  end as risk_level,
  case
    when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
      then 'Schema privilege finding is part of a truncated bounded sample; review coverage flags before treating the inventory as complete'
    when findings.grantee = 0 and findings.privilege_type = 'CREATE' then 'PUBLIC can create objects in a non-public schema'
    when findings.grantee = 0 then 'PUBLIC has schema privileges; USAGE alone may be intentional and requires a baseline comparison'
    when findings.privilege_type = 'CREATE' then 'non-owner role can create objects in schema'
    when findings.is_grantable then 'schema privilege can be granted onward'
    else 'informational schema privilege'
  end as risk_reason
from findings
cross join coverage
union all
select
  '[coverage]'::text,
  ''::text,
  ''::text,
  ''::text,
  ''::text,
  false,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  coverage.result_truncated,
  'unknown'::text,
  'The bounded schema candidate, ACL expansion, or result sample was truncated; absence of findings is not a clean result'::text
from coverage
where coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
order by
  risk_level desc,
  schema_name asc,
  grantee asc,
  privilege_type asc
