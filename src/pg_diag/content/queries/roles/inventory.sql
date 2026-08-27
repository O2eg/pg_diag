with roles_bounded as (
  select
    r.oid,
    r.rolname,
    r.rolcanlogin,
    r.rolsuper,
    r.rolinherit,
    r.rolcreaterole,
    r.rolcreatedb,
    r.rolreplication,
    r.rolbypassrls,
    r.rolconnlimit,
    r.rolvaliduntil
  from pg_catalog.pg_roles r
  order by r.rolname, r.oid
  limit 5001
),
roles_sample as (
  select * from roles_bounded limit 5000
),
membership_bounded as (
  select am.member, am.roleid
  from pg_catalog.pg_auth_members am
  order by am.member, am.roleid
  limit 20001
),
membership_sample as (
  select * from membership_bounded limit 20000
),
member_of as (
  select
    m.member as role_oid,
    count(*)::int8 as member_of_count,
    string_agg(g.rolname::text, ', ' order by g.rolname) as member_of
  from membership_sample m
  join pg_catalog.pg_roles g on g.oid = m.roleid
  group by m.member
),
members as (
  select
    m.roleid as role_oid,
    count(*)::int8 as direct_member_count
  from membership_sample m
  group by m.roleid
),
role_settings as (
  select
    s.setrole as role_oid,
    sum(coalesce(array_length(s.setconfig, 1), 0))::int8 as setting_count
  from pg_catalog.pg_db_role_setting s
  where s.setrole <> 0
  group by s.setrole
),
coverage as (
  select
    (select count(*) > 5000 from roles_bounded) as role_sample_truncated,
    (select count(*) > 20000 from membership_bounded) as membership_sample_truncated
)
select
  r.rolname::text as role_name,
  r.oid as role_oid,
  r.rolcanlogin as can_login,
  r.rolsuper as superuser,
  r.rolinherit as inherit,
  r.rolcreaterole as create_role,
  r.rolcreatedb as create_db,
  r.rolreplication as replication,
  r.rolbypassrls as bypass_rls,
  r.rolconnlimit as connection_limit,
  case when r.rolvaliduntil = 'infinity' then null else r.rolvaliduntil end as valid_until,
  (r.rolvaliduntil is not null and r.rolvaliduntil < now()) as valid_until_expired,
  (r.rolname ~ '^pg_') as is_predefined,
  coalesce(mo.member_of_count, 0)::int8 as member_of_count,
  mo.member_of,
  coalesce(mb.direct_member_count, 0)::int8 as direct_member_count,
  coalesce(rs.setting_count, 0)::int8 as setting_count,
  d.description as comment,
  coverage.role_sample_truncated,
  coverage.membership_sample_truncated,
  case
    when coverage.role_sample_truncated or coverage.membership_sample_truncated then 'unknown'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when coverage.role_sample_truncated
      then 'More than 5000 roles exist; the inventory shows the first 5000 by name'
    when coverage.membership_sample_truncated
      then 'More than 20000 role memberships exist; member_of and member counts are partial'
    else ''
  end as pg_diag_internal_reason
from roles_sample r
left join member_of mo on mo.role_oid = r.oid
left join members mb on mb.role_oid = r.oid
left join role_settings rs on rs.role_oid = r.oid
left join pg_catalog.pg_shdescription d
  on d.objoid = r.oid and d.classoid = 'pg_catalog.pg_authid'::regclass
cross join coverage
order by is_predefined asc, r.rolcanlogin desc, r.rolname asc
