with default_acl_roots_bounded as (
  select
    d.oid,
    d.defaclrole,
    d.defaclnamespace,
    d.defaclobjtype,
    d.defaclacl
  from pg_catalog.pg_default_acl d
  left join pg_catalog.pg_namespace n on n.oid = d.defaclnamespace
  order by
    pg_catalog.pg_get_userbyid(d.defaclrole),
    coalesce(n.nspname, ''),
    d.defaclobjtype,
    d.oid
  limit 10001
),
default_acl_candidates as (
  select *
  from default_acl_roots_bounded
  limit 10000
),
expanded_default_acl_bounded as (
  select
    d.defaclrole,
    d.defaclnamespace,
    d.defaclobjtype,
    acl.grantor,
    acl.grantee,
    acl.privilege_type,
    acl.is_grantable
  from default_acl_candidates d
  cross join lateral pg_catalog.aclexplode(d.defaclacl) as acl
  where acl.grantee = 0
     or (acl.is_grantable and acl.grantee <> d.defaclrole)
  limit 3001
),
expanded_default_acl as (
  select *
  from expanded_default_acl_bounded
  limit 3000
),
normalized as (
  select
    pg_catalog.pg_get_userbyid(defaclrole)::text as owner_name,
    case
      when defaclnamespace = 0 then '<all schemas>'
      else defaclnamespace::regnamespace::text
    end as schema_name,
    case defaclobjtype
      when 'r' then 'tables'
      when 'S' then 'sequences'
      when 'f' then 'functions'
      when 'T' then 'types'
      when 'n' then 'schemas'
      else defaclobjtype::text
    end as object_type,
    case when grantee = 0 then 'PUBLIC' else pg_catalog.pg_get_userbyid(grantee)::text end as grantee,
    pg_catalog.pg_get_userbyid(grantor)::text as grantor,
    privilege_type,
    is_grantable
  from expanded_default_acl
),
ranked_findings as (
  select *
  from normalized
  order by owner_name, schema_name, object_type, grantee, privilege_type
  limit 1001
),
coverage as (
  select
    (select count(*) > 10000 from default_acl_roots_bounded) as candidate_sample_truncated,
    (select count(*) > 3000 from expanded_default_acl_bounded) as acl_expansion_truncated,
    (select count(*) > 1000 from ranked_findings) as result_truncated
),
findings as (
  select *
  from ranked_findings
  limit 1000
)
select
  findings.owner_name,
  findings.schema_name,
  findings.object_type,
  findings.grantee,
  findings.grantor,
  findings.privilege_type,
  findings.is_grantable,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  coverage.result_truncated,
  case
    when findings.grantee = 'PUBLIC' and findings.privilege_type in ('CREATE', 'EXECUTE', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'USAGE') then 'high'
    when findings.grantee = 'PUBLIC' then 'medium'
    when findings.is_grantable then 'medium'
    else 'ok'
  end as risk_level,
  case
    when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
      then 'Default privilege finding is part of a truncated bounded sample; review coverage flags before treating the inventory as complete'
    when findings.grantee = 'PUBLIC' then 'future objects will grant privileges to PUBLIC'
    when findings.is_grantable then 'future object privilege can be granted onward'
    else 'informational default privilege'
  end as risk_reason
from findings
cross join coverage
union all
select
  '[coverage]'::text,
  ''::text,
  'coverage'::text,
  ''::text,
  ''::text,
  ''::text,
  false,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  coverage.result_truncated,
  'unknown'::text,
  'The bounded default-ACL candidate, ACL expansion, or result sample was truncated; absence of findings is not a clean result'::text
from coverage
where coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
order by
  risk_level desc,
  owner_name asc,
  schema_name asc,
  object_type asc,
  grantee asc,
  privilege_type asc
