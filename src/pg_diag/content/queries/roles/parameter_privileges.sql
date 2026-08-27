with parameters_bounded as (
  select p.oid, p.parname, p.paracl
  from pg_catalog.pg_parameter_acl p
  order by p.parname, p.oid
  limit 1001
),
parameters as (
  select * from parameters_bounded limit 1000
),
grants_bounded as (
  select
    p.parname,
    e.grantee,
    e.grantor,
    e.privilege_type,
    e.is_grantable
  from parameters p
  cross join lateral aclexplode(p.paracl) e
  limit 3001
),
grants as (
  select * from grants_bounded limit 3000
),
coverage as (
  select
    (select count(*) > 1000 from parameters_bounded) as candidate_sample_truncated,
    (select count(*) > 3000 from grants_bounded) as acl_expansion_truncated
)
select
  g.parname::text as parameter_name,
  coalesce(gr.rolname::text, 'PUBLIC') as grantee_name,
  case
    when gr.oid is null then 'PUBLIC'
    when gr.rolcanlogin then 'login role'
    else 'group role'
  end as grantee_kind,
  coalesce(gr.rolsuper, false) as grantee_is_superuser,
  g.privilege_type,
  g.is_grantable,
  pg_catalog.pg_get_userbyid(g.grantor)::text as grantor,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  case
    when coalesce(gr.rolsuper, false) then 'ok'
    when g.privilege_type = 'ALTER SYSTEM' then 'medium'
    else 'unknown'
  end as risk_level,
  case
    when coalesce(gr.rolsuper, false)
      then 'Superuser already holds every parameter privilege; this entry records the grantor side of the ACL'
    when g.privilege_type = 'ALTER SYSTEM'
      then 'Non-superuser can change this server parameter persistently through ALTER SYSTEM'
    else 'Non-superuser can set this restricted parameter in its sessions; compare with the intended configuration baseline'
  end as risk_reason
from grants g
left join pg_catalog.pg_roles gr on gr.oid = g.grantee
cross join coverage
union all
select
  '[coverage]'::text,
  ''::text,
  ''::text,
  false,
  ''::text,
  false,
  ''::text,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  'unknown'::text,
  'Parameter ACL sample was truncated; findings above are proven but the list is incomplete'::text
from coverage
where coverage.candidate_sample_truncated or coverage.acl_expansion_truncated
order by parameter_name, grantee_name, privilege_type
