with recursive closure(member, role, depth, path, inherits, can_set) as (
  select
    am.member,
    am.roleid,
    1,
    array[am.member, am.roleid],
    am.inherit_option,
    am.set_option
  from pg_catalog.pg_auth_members am
  join pg_catalog.pg_roles m on m.oid = am.member
  where m.rolname !~ '^pg_'

  union all

  select
    c.member,
    am.roleid,
    c.depth + 1,
    c.path || am.roleid,
    c.inherits and am.inherit_option,
    c.can_set and am.set_option
  from closure c
  join pg_catalog.pg_auth_members am on am.member = c.role
  where not am.roleid = any(c.path)
    and c.depth < 32
),
closure_bounded as (
  select * from closure limit 3001
),
closure_sample as (
  select * from closure_bounded limit 3000
),
coverage as (
  select (select count(*) > 3000 from closure_bounded) as membership_truncated
),
findings as (
  select
    m.rolname::text as member_role,
    m.rolcanlogin as member_can_login,
    m.rolsuper as member_is_superuser,
    r.rolname::text as inherited_role,
    r.rolcanlogin as inherited_role_can_login,
    r.rolsuper as inherited_role_is_superuser,
    (r.rolname ~ '^pg_') as inherited_role_is_predefined,
    concat_ws(
      ', ',
      case when r.rolcreaterole then 'CREATEROLE' end,
      case when r.rolcreatedb then 'CREATEDB' end,
      case when r.rolreplication then 'REPLICATION' end,
      case when r.rolbypassrls then 'BYPASSRLS' end
    ) as inherited_role_attributes,
    c.depth::int8 as depth,
    (
      select string_agg(pr.rolname::text, ' -> ' order by u.ord)
      from unnest(c.path) with ordinality u(role_oid, ord)
      join pg_catalog.pg_roles pr on pr.oid = u.role_oid
    ) as path,
    c.inherits as inherits_privileges,
    c.can_set as can_set_role,
    coverage.membership_truncated
  from closure_sample c
  join pg_catalog.pg_roles m on m.oid = c.member
  join pg_catalog.pg_roles r on r.oid = c.role
  cross join coverage
),
combined as (
select
  f.member_role,
  f.member_can_login,
  f.member_is_superuser,
  f.inherited_role,
  f.inherited_role_can_login,
  f.inherited_role_is_superuser,
  f.inherited_role_is_predefined,
  f.inherited_role_attributes,
  f.depth,
  f.path,
  f.inherits_privileges,
  f.can_set_role,
  f.membership_truncated,
  case
    when f.membership_truncated then 'unknown'
    when f.inherited_role_is_superuser and not f.member_is_superuser and f.can_set_role then 'high'
    when f.inherited_role_attributes <> '' and not f.member_is_superuser and f.can_set_role then 'medium'
    when f.inherited_role_is_predefined and not f.member_is_superuser
      and (f.inherits_privileges or f.can_set_role) then 'medium'
    else 'ok'
  end as risk_level,
  case
    when f.membership_truncated
      then 'Role membership traversal exceeded 3000 rows; the effective membership list is partial'
    when f.inherited_role_is_superuser and not f.member_is_superuser and f.can_set_role
      then 'Non-superuser role can become a superuser role through SET ROLE'
    when f.inherited_role_attributes <> '' and not f.member_is_superuser and f.can_set_role
      then 'Non-superuser role can obtain ' || f.inherited_role_attributes || ' through SET ROLE'
    when f.inherited_role_is_predefined and not f.member_is_superuser
      and (f.inherits_privileges or f.can_set_role)
      then 'Role reaches a predefined PostgreSQL administrative role'
    else ''
  end as risk_reason
from findings f
union all
select
  '[coverage]'::text,
  false,
  false,
  '[multiple roles]'::text,
  false,
  false,
  false,
  ''::text,
  null::int8,
  null::text,
  false,
  false,
  true,
  'unknown'::text,
  'Role membership traversal exceeded 3000 rows; the bounded list is partial and an empty result is not a clean result'::text
from coverage
where coverage.membership_truncated
)
select *
from combined
order by
  case risk_level when 'high' then 0 when 'medium' then 1 when 'unknown' then 2 else 3 end,
  member_role,
  depth,
  inherited_role
