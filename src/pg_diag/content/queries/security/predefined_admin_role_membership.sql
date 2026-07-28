with recursive predefined_admin_roles(role_name) as (
  values
    ('pg_monitor'),
    ('pg_read_all_settings'),
    ('pg_read_all_stats'),
    ('pg_stat_scan_tables'),
    ('pg_signal_backend'),
    ('pg_read_server_files'),
    ('pg_write_server_files'),
    ('pg_execute_server_program'),
    ('pg_read_all_data'),
    ('pg_write_all_data'),
    ('pg_use_reserved_connections'),
    ('pg_signal_autovacuum_worker'),
    ('pg_checkpoint'),
    ('pg_maintain'),
    ('pg_create_subscription')
),
admin_roles as (
  select r.oid, r.rolname
  from pg_catalog.pg_roles r
  join predefined_admin_roles wanted on wanted.role_name = r.rolname
),
role_membership(member, admin_role_oid, depth, path) as (
  select
    am.member,
    admin.oid,
    1 as depth,
    array[admin.oid, am.member] as path
  from admin_roles admin
  join pg_catalog.pg_auth_members am on am.roleid = admin.oid

  union all

  select
    am.member,
    rm.admin_role_oid,
    rm.depth + 1,
    rm.path || am.member
  from role_membership rm
  join pg_catalog.pg_auth_members am on am.roleid = rm.member
  where not am.member = any(rm.path)
),
bounded_role_membership as (
  select *
  from role_membership
  limit 3001
),
limited_role_membership as (
  select *
  from bounded_role_membership
  limit 3000
),
membership_coverage as (
  select (count(*) > 3000) as membership_truncated
  from bounded_role_membership
),
findings as (
  select
    member_role.rolname as member_role,
    member_role.rolcanlogin as member_can_login,
    admin_role.rolname as inherited_admin_role,
    min(rm.depth)::int8 as grant_depth,
    coverage.membership_truncated,
    case
      when admin_role.rolname in (
        'pg_execute_server_program',
        'pg_write_server_files',
        'pg_write_all_data',
        'pg_create_subscription'
      ) then 'high'
      when admin_role.rolname in (
        'pg_read_server_files',
        'pg_read_all_data',
        'pg_signal_backend',
        'pg_signal_autovacuum_worker',
        'pg_use_reserved_connections',
        'pg_checkpoint',
        'pg_maintain'
      ) then 'medium'
      else 'medium'
    end as risk_level,
    case
      when coverage.membership_truncated then 'Administrative role-membership traversal exceeded 3000 rows; findings are partial'
      when admin_role.rolname = 'pg_execute_server_program' then 'can execute server-side programs'
      when admin_role.rolname = 'pg_write_server_files' then 'can write server-side files'
      when admin_role.rolname = 'pg_read_server_files' then 'can read server-side files'
      when admin_role.rolname = 'pg_write_all_data' then 'can write all data'
      when admin_role.rolname = 'pg_read_all_data' then 'can read all data'
      when admin_role.rolname = 'pg_create_subscription' then 'can create subscriptions'
      when admin_role.rolname = 'pg_signal_backend' then 'can signal backend processes'
      when admin_role.rolname = 'pg_signal_autovacuum_worker' then 'can signal autovacuum worker processes'
      when admin_role.rolname = 'pg_use_reserved_connections' then 'can consume reserved connection slots'
      else 'inherits PostgreSQL predefined administrative role'
    end as risk_reason
  from limited_role_membership rm
  join pg_catalog.pg_roles member_role on member_role.oid = rm.member
  join admin_roles admin_role on admin_role.oid = rm.admin_role_oid
  cross join membership_coverage coverage
  where not member_role.rolsuper
    and member_role.rolname !~ '^pg_'
  group by
    member_role.rolname,
    member_role.rolcanlogin,
    admin_role.rolname,
    coverage.membership_truncated
),
coverage_notice as (
  select
    '[coverage]'::name as member_role,
    false as member_can_login,
    '[multiple predefined roles]'::name as inherited_admin_role,
    null::int8 as grant_depth,
    true as membership_truncated,
    'unknown'::text as risk_level,
    'Administrative role-membership traversal exceeded 3000 rows; the bounded findings are partial and an empty finding set is not a clean result'::text as risk_reason
  from membership_coverage
  where membership_truncated
)
select
  *
from findings
union all
select
  *
from coverage_notice
order by
  risk_level desc,
  member_can_login desc,
  member_role asc,
  inherited_admin_role asc
