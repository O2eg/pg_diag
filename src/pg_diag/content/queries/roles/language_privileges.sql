with languages_bounded as (
  select l.oid, l.lanname, l.lanpltrusted, l.lanowner, l.lanacl
  from pg_catalog.pg_language l
  where l.lanispl
  order by l.lanname, l.oid
  limit 201
),
languages as (
  select * from languages_bounded limit 200
),
grants_bounded as (
  select
    l.lanname,
    l.lanpltrusted,
    l.lanowner,
    (l.lanacl is null) as acl_is_default,
    e.grantee,
    e.grantor,
    e.privilege_type,
    e.is_grantable
  from languages l
  cross join lateral aclexplode(coalesce(l.lanacl, acldefault('l', l.lanowner))) e
  where e.grantee <> l.lanowner
  limit 3001
),
grants as (
  select * from grants_bounded limit 3000
),
coverage as (
  select
    (select count(*) > 200 from languages_bounded) as candidate_sample_truncated,
    (select count(*) > 3000 from grants_bounded) as acl_expansion_truncated
)
select
  g.lanname::text as language_name,
  g.lanpltrusted as is_trusted,
  pg_catalog.pg_get_userbyid(g.lanowner)::text as language_owner,
  coalesce(gr.rolname::text, 'PUBLIC') as grantee_name,
  case
    when gr.oid is null then 'PUBLIC'
    when gr.rolcanlogin then 'login role'
    else 'group role'
  end as grantee_kind,
  g.privilege_type,
  g.is_grantable,
  pg_catalog.pg_get_userbyid(g.grantor)::text as grantor,
  g.acl_is_default,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  case
    when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated then 'unknown'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated
      then 'Language or ACL sample was truncated; language privileges are partial'
    else ''
  end as pg_diag_internal_reason
from grants g
left join pg_catalog.pg_roles gr on gr.oid = g.grantee
cross join coverage
order by language_name, grantee_name, privilege_type
