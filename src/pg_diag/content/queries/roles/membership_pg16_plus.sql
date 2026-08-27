with edges_bounded as (
  select am.roleid, am.member, am.grantor, am.admin_option, am.inherit_option, am.set_option
  from pg_catalog.pg_auth_members am
  order by am.member, am.roleid
  limit 5001
),
edges as (
  select * from edges_bounded limit 5000
),
coverage as (
  select (select count(*) > 5000 from edges_bounded) as result_truncated
)
select
  m.rolname::text as member_role,
  m.rolcanlogin as member_can_login,
  m.rolinherit as member_inherits_by_default,
  g.rolname::text as granted_role,
  g.rolcanlogin as granted_role_can_login,
  g.rolsuper as granted_role_is_superuser,
  (g.rolname ~ '^pg_') as granted_role_is_predefined,
  gr.rolname::text as grantor,
  e.admin_option,
  e.inherit_option,
  e.set_option,
  coverage.result_truncated,
  case when coverage.result_truncated then 'unknown' else 'ok' end as pg_diag_internal_severity,
  case
    when coverage.result_truncated
      then 'More than 5000 role memberships exist; the membership list is partial'
    else ''
  end as pg_diag_internal_reason
from edges e
join pg_catalog.pg_roles m on m.oid = e.member
join pg_catalog.pg_roles g on g.oid = e.roleid
left join pg_catalog.pg_roles gr on gr.oid = e.grantor
cross join coverage
order by member_role, granted_role
