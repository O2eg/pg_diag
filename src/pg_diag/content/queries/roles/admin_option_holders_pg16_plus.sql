with admin_edges_bounded as (
  select am.member, am.roleid, am.grantor
  from pg_catalog.pg_auth_members am
  where am.admin_option
  order by am.member, am.roleid
  limit 3001
),
admin_edges as (
  select * from admin_edges_bounded limit 3000
),
createrole_roles_bounded as (
  select r.oid, r.rolname, r.rolcanlogin, r.rolsuper
  from pg_catalog.pg_roles r
  where r.rolcreaterole
    and r.rolname !~ '^pg_'
  order by r.rolname, r.oid
  limit 1001
),
createrole_roles as (
  select * from createrole_roles_bounded limit 1000
),
findings as (
  select
    m.rolname::text as role_name,
    m.rolcanlogin as can_login,
    m.rolsuper as superuser,
    'ADMIN OPTION'::text as administration_source,
    g.rolname::text as administered_role,
    gr.rolname::text as grantor
  from admin_edges e
  join pg_catalog.pg_roles m on m.oid = e.member
  join pg_catalog.pg_roles g on g.oid = e.roleid
  left join pg_catalog.pg_roles gr on gr.oid = e.grantor

  union all

  select
    r.rolname::text,
    r.rolcanlogin,
    r.rolsuper,
    'CREATEROLE'::text,
    '[roles created by this role]'::text,
    null::text
  from createrole_roles r
),
coverage as (
  select
    (
      (select count(*) > 3000 from admin_edges_bounded)
      or (select count(*) > 1000 from createrole_roles_bounded)
    ) as result_truncated
),
combined as (
select
  f.role_name,
  f.can_login,
  f.superuser,
  f.administration_source,
  f.administered_role,
  f.grantor,
  coverage.result_truncated,
  case
    when f.superuser then 'ok'
    else 'medium'
  end as risk_level,
  case
    when f.superuser
      then 'Superuser already administers every role'
    when f.administration_source = 'CREATEROLE'
      then 'CREATEROLE lets this role manage the roles it created; ADMIN OPTION rows show the exact administered roles on PostgreSQL 16 and newer'
    else 'Role can grant or revoke membership in the administered role'
  end as risk_reason
from findings f
cross join coverage
union all
select
  '[coverage]'::text,
  false,
  false,
  ''::text,
  ''::text,
  null::text,
  true,
  'unknown'::text,
  'Administrative membership sample was truncated; findings above are proven but the list is incomplete'::text
from coverage
where coverage.result_truncated
)
select *
from combined
order by
  case risk_level when 'medium' then 0 when 'unknown' then 1 else 2 end,
  role_name,
  administration_source,
  administered_role
