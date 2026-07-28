with sequence_roots_bounded as (
  select
    c.oid,
    c.relname,
    c.relowner,
    c.relacl,
    n.nspname
  from pg_catalog.pg_class c
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where c.relkind = 'S'
    and n.nspname not in ('pg_catalog', 'information_schema', 'pg_toast')
    and n.nspname not like 'pg_temp_%'
    and n.nspname not like 'pg_toast_temp_%'
  order by n.nspname, c.relname, c.oid
  limit 10001
),
sequence_candidates as (
  select *
  from sequence_roots_bounded
  limit 10000
),
sequence_acl_bounded as (
  select
    c.nspname::text as schema_name,
    c.relname::text as sequence_name,
    pg_catalog.pg_get_userbyid(c.relowner)::text as owner_name,
    acl.grantor,
    acl.grantee,
    acl.privilege_type,
    acl.is_grantable
  from sequence_candidates c
  cross join lateral pg_catalog.aclexplode(
    coalesce(c.relacl, pg_catalog.acldefault('S', c.relowner))
  ) as acl
  where acl.grantee = 0
     or (acl.is_grantable and acl.grantee <> c.relowner)
  limit 3001
),
sequence_acl as (
  select *
  from sequence_acl_bounded
  limit 3000
),
ranked_findings as (
  select *
  from sequence_acl
  order by schema_name, sequence_name, grantee, privilege_type
  limit 1001
),
coverage as (
  select
    (select count(*) > 10000 from sequence_roots_bounded) as candidate_sample_truncated,
    (select count(*) > 3000 from sequence_acl_bounded) as acl_expansion_truncated,
    (select count(*) > 1000 from ranked_findings) as result_truncated
),
findings as (
  select *
  from ranked_findings
  limit 1000
)
select
  findings.schema_name,
  findings.sequence_name,
  findings.owner_name,
  case when findings.grantee = 0 then 'PUBLIC' else pg_catalog.pg_get_userbyid(findings.grantee)::text end as grantee,
  pg_catalog.pg_get_userbyid(findings.grantor)::text as grantor,
  findings.privilege_type,
  findings.is_grantable,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  coverage.result_truncated,
  case
    when findings.grantee = 0 and findings.privilege_type in ('USAGE', 'UPDATE') then 'high'
    when findings.grantee = 0 then 'medium'
    when findings.is_grantable then 'medium'
    else 'ok'
  end as risk_level,
  case
    when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
      then 'Sequence privilege finding is part of a truncated bounded sample; review coverage flags before treating the inventory as complete'
    when findings.grantee = 0 then 'sequence privilege is granted to PUBLIC'
    when findings.is_grantable then 'sequence privilege can be granted onward'
    else 'informational sequence privilege'
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
  ''::text,
  false,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  coverage.result_truncated,
  'unknown'::text,
  'The bounded sequence candidate, ACL expansion, or result sample was truncated; absence of findings is not a clean result'::text
from coverage
where coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
order by
  risk_level desc,
  schema_name asc,
  sequence_name asc,
  grantee asc,
  privilege_type asc
