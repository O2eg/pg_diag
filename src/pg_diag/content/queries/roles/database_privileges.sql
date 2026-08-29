with databases_bounded as (
  select d.oid, d.datname, d.datdba, d.datacl, d.datallowconn
  from pg_catalog.pg_database d
  order by d.datname, d.oid
  limit 1001
),
databases as (
  select * from databases_bounded limit 1000
),
grants_bounded as (
  select
    db.oid,
    db.datname,
    db.datdba,
    db.datallowconn,
    (db.datacl is null) as acl_is_default,
    e.grantee,
    e.grantor,
    e.privilege_type,
    e.is_grantable
  from databases db
  cross join lateral aclexplode(coalesce(db.datacl, acldefault('d', db.datdba))) e
  where e.grantee <> db.datdba
  limit 3001
),
grants as (
  select * from grants_bounded limit 3000
),
coverage as (
  select
    (select count(*) > 1000 from databases_bounded) as candidate_sample_truncated,
    (select count(*) > 3000 from grants_bounded) as acl_expansion_truncated
)
select
  g.datname::text as database_name,
  g.oid::int8 as database_oid,
  pg_catalog.pg_get_userbyid(g.datdba)::text as database_owner,
  g.datallowconn as allows_connections,
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
    when coverage.candidate_sample_truncated
      then 'More than 1000 databases exist; database privileges are partial'
    when coverage.acl_expansion_truncated
      then 'More than 3000 database ACL entries exist; database privileges are partial'
    else ''
  end as pg_diag_internal_reason
from grants g
left join pg_catalog.pg_roles gr on gr.oid = g.grantee
cross join coverage
order by database_name, grantee_name, g.privilege_type
