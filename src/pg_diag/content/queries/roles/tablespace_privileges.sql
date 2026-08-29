with tablespaces_bounded as (
  select t.oid, t.spcname, t.spcowner, t.spcacl
  from pg_catalog.pg_tablespace t
  order by t.spcname, t.oid
  limit 1001
),
tablespaces as (
  select * from tablespaces_bounded limit 1000
),
grants_bounded as (
  select
    t.spcname,
    t.spcowner,
    e.grantee,
    e.grantor,
    e.privilege_type,
    e.is_grantable
  from tablespaces t
  cross join lateral aclexplode(t.spcacl) e
  where e.grantee <> t.spcowner
  limit 3001
),
grants as (
  select * from grants_bounded limit 3000
),
coverage as (
  select
    (select count(*) > 1000 from tablespaces_bounded) as candidate_sample_truncated,
    (select count(*) > 3000 from grants_bounded) as acl_expansion_truncated
)
select
  g.spcname::text as tablespace_name,
  pg_catalog.pg_get_userbyid(g.spcowner)::text as tablespace_owner,
  coalesce(gr.rolname::text, 'PUBLIC') as grantee_name,
  gr.oid::int8 as grantee_oid,
  case
    when gr.oid is null then 'PUBLIC'
    when gr.rolcanlogin then 'login role'
    else 'group role'
  end as grantee_kind,
  g.privilege_type,
  g.is_grantable,
  pg_catalog.pg_get_userbyid(g.grantor)::text as grantor,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  case
    when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated then 'unknown'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated
      then 'Tablespace or ACL sample was truncated; tablespace privileges are partial'
    else ''
  end as pg_diag_internal_reason
from grants g
left join pg_catalog.pg_roles gr on gr.oid = g.grantee
cross join coverage
union all
select
  '[coverage]'::text,
  ''::text,
  ''::text,
  null::int8,
  ''::text,
  ''::text,
  false,
  ''::text,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  'unknown'::text,
  'Tablespace or ACL sample was truncated; an empty result is not a clean result'::text
from coverage
where coverage.candidate_sample_truncated or coverage.acl_expansion_truncated
order by tablespace_name, grantee_name, privilege_type
