with defaults_bounded as (
  select d.oid, d.defaclrole, d.defaclnamespace, d.defaclobjtype, d.defaclacl
  from pg_catalog.pg_default_acl d
  order by d.oid
  limit 1001
),
defaults as (
  select * from defaults_bounded limit 1000
),
grants_bounded as (
  select
    d.defaclrole,
    d.defaclnamespace,
    d.defaclobjtype,
    e.grantee,
    e.grantor,
    e.privilege_type,
    e.is_grantable
  from defaults d
  cross join lateral aclexplode(d.defaclacl) e
  where e.grantee <> d.defaclrole
  limit 3001
),
grants as (
  select * from grants_bounded limit 3000
),
coverage as (
  select
    (select count(*) > 1000 from defaults_bounded) as candidate_sample_truncated,
    (select count(*) > 3000 from grants_bounded) as acl_expansion_truncated
)
select
  pg_catalog.pg_get_userbyid(g.defaclrole)::text as defining_role,
  coalesce(n.nspname::text, '[all schemas]') as schema_name,
  case g.defaclobjtype
    when 'r' then 'table'
    when 'S' then 'sequence'
    when 'f' then 'function'
    when 'T' then 'type'
    when 'n' then 'schema'
    else g.defaclobjtype::text
  end as object_type,
  coalesce(gr.rolname::text, 'PUBLIC') as grantee_name,
  case
    when gr.oid is null then 'PUBLIC'
    when gr.rolcanlogin then 'login role'
    else 'group role'
  end as grantee_kind,
  g.privilege_type,
  g.is_grantable,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  case
    when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated then 'unknown'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated
      then 'Default privilege sample was truncated; the list is partial'
    else ''
  end as pg_diag_internal_reason
from grants g
left join pg_catalog.pg_namespace n on n.oid = g.defaclnamespace
left join pg_catalog.pg_roles gr on gr.oid = g.grantee
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
  'unknown'::text,
  'Default privilege sample was truncated; an empty result is not a clean result'::text
from coverage
where coverage.candidate_sample_truncated or coverage.acl_expansion_truncated
order by defining_role, schema_name, object_type, grantee_name, privilege_type
