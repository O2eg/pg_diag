with candidates_bounded as (
  select
    r.oid,
    r.rolname,
    r.rolsuper,
    r.rolinherit,
    r.rolcreaterole,
    r.rolcreatedb,
    r.rolreplication,
    r.rolbypassrls
  from pg_catalog.pg_roles r
  where not r.rolcanlogin
    and r.rolname !~ '^pg_'
    and not exists (
      select 1
      from pg_catalog.pg_auth_members am
      where am.roleid = r.oid
    )
  order by r.rolname, r.oid
  limit 1001
),
candidates as (
  select * from candidates_bounded limit 1000
),
member_of as (
  select
    am.member as role_oid,
    count(*)::int8 as member_of_count,
    string_agg(g.rolname::text, ', ' order by g.rolname) as member_of
  from pg_catalog.pg_auth_members am
  join candidates c on c.oid = am.member
  join pg_catalog.pg_roles g on g.oid = am.roleid
  group by am.member
),
role_settings as (
  select
    s.setrole as role_oid,
    sum(coalesce(array_length(s.setconfig, 1), 0))::int8 as setting_count
  from pg_catalog.pg_db_role_setting s
  join candidates c on c.oid = s.setrole
  group by s.setrole
),
database_grants as (
  select
    e.grantee as role_oid,
    count(*)::int8 as database_privilege_count
  from pg_catalog.pg_database d
  cross join lateral aclexplode(d.datacl) e
  join candidates c on c.oid = e.grantee
  group by e.grantee
),
default_grants as (
  select
    e.grantee as role_oid,
    count(*)::int8 as default_privilege_count
  from pg_catalog.pg_default_acl da
  cross join lateral aclexplode(da.defaclacl) e
  join candidates c on c.oid = e.grantee
  group by e.grantee
),
coverage as (
  select (select count(*) > 1000 from candidates_bounded) as result_truncated
)
select
  c.rolname::text as role_name,
  c.oid as role_oid,
  c.rolsuper as superuser,
  c.rolinherit as inherit,
  c.rolcreaterole as create_role,
  c.rolcreatedb as create_db,
  c.rolreplication as replication,
  c.rolbypassrls as bypass_rls,
  coalesce(mo.member_of_count, 0)::int8 as member_of_count,
  mo.member_of,
  coalesce(rs.setting_count, 0)::int8 as setting_count,
  coalesce(dg.database_privilege_count, 0)::int8 as database_privilege_count,
  coalesce(df.default_privilege_count, 0)::int8 as default_privilege_count,
  d.description as comment,
  coverage.result_truncated,
  'unknown'::text as risk_level,
  case
    when coverage.result_truncated
      then 'More than 1000 group roles without members exist; the list is partial'
    else 'No role is a member of this group role; verify whether it is still required as an owner, grantee, or template role'
  end as risk_reason
from candidates c
left join member_of mo on mo.role_oid = c.oid
left join role_settings rs on rs.role_oid = c.oid
left join database_grants dg on dg.role_oid = c.oid
left join default_grants df on df.role_oid = c.oid
left join pg_catalog.pg_shdescription d
  on d.objoid = c.oid and d.classoid = 'pg_catalog.pg_authid'::regclass
cross join coverage
order by c.rolsuper desc, c.rolname asc
