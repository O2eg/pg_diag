with edges_bounded as (
  select am.roleid, am.member
  from pg_catalog.pg_auth_members am
  order by am.roleid, am.member
  limit 20001
),
edges_sample as (
  select * from edges_bounded limit 20000
),
grouped_bounded as (
  select
    e.roleid as role_oid,
    count(*)::int8 as direct_member_count,
    left(
      string_agg(m.rolname::text, ', ' order by m.rolname) filter (where m.rolcanlogin),
      500
    ) as login_members,
    left(
      string_agg(m.rolname::text, ', ' order by m.rolname) filter (where not m.rolcanlogin),
      500
    ) as nologin_members
  from edges_sample e
  join pg_catalog.pg_roles m on m.oid = e.member
  group by e.roleid
  order by direct_member_count desc, e.roleid
  limit 5001
),
grouped_sample as (
  select * from grouped_bounded limit 5000
),
coverage as (
  select
    (select count(*) > 20000 from edges_bounded) as membership_sample_truncated,
    (select count(*) > 5000 from grouped_bounded) as role_sample_truncated
)
select
  g.rolname::text as role_name,
  g.rolcanlogin as can_login,
  (g.rolname ~ '^pg_') as is_predefined,
  gr.direct_member_count,
  gr.login_members,
  gr.nologin_members,
  coverage.membership_sample_truncated,
  coverage.role_sample_truncated,
  case
    when coverage.membership_sample_truncated or coverage.role_sample_truncated then 'unknown'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when coverage.membership_sample_truncated
      then 'More than 20000 role memberships exist; member lists and counts are partial'
    when coverage.role_sample_truncated
      then 'More than 5000 roles have direct members; the list shows the first 5000 by member count'
    else ''
  end as pg_diag_internal_reason
from grouped_sample gr
join pg_catalog.pg_roles g on g.oid = gr.role_oid
cross join coverage
order by direct_member_count desc, is_predefined asc, role_name asc
