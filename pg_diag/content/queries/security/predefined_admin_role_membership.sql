with recursive role_membership(member, roleid, depth, path) as (
  select
    member,
    roleid,
    1 as depth,
    array[member, roleid] as path
  from pg_catalog.pg_auth_members

  union all

  select
    rm.member,
    am.roleid,
    rm.depth + 1 as depth,
    rm.path || am.roleid
  from role_membership rm
  join pg_catalog.pg_auth_members am on am.member = rm.roleid
  where not am.roleid = any(rm.path)
),
predefined_admin_roles(role_name) as (
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
    ('pg_checkpoint'),
    ('pg_maintain'),
    ('pg_create_subscription')
)
select
  member_role.rolname as member_role,
  member_role.rolcanlogin as member_can_login,
  admin_role.rolname as inherited_admin_role,
  min(rm.depth)::int8 as grant_depth,
  case
    when admin_role.rolname in ('pg_execute_server_program', 'pg_write_server_files', 'pg_write_all_data', 'pg_create_subscription') then 'high'
    when admin_role.rolname in ('pg_read_server_files', 'pg_read_all_data', 'pg_signal_backend', 'pg_checkpoint', 'pg_maintain') then 'medium'
    else 'medium'
  end as risk_level,
  case
    when admin_role.rolname = 'pg_execute_server_program' then 'can execute server-side programs'
    when admin_role.rolname = 'pg_write_server_files' then 'can write server-side files'
    when admin_role.rolname = 'pg_read_server_files' then 'can read server-side files'
    when admin_role.rolname = 'pg_write_all_data' then 'can write all data'
    when admin_role.rolname = 'pg_read_all_data' then 'can read all data'
    when admin_role.rolname = 'pg_create_subscription' then 'can create subscriptions'
    when admin_role.rolname = 'pg_signal_backend' then 'can signal backend processes'
    else 'inherits PostgreSQL predefined administrative role'
  end as risk_reason
from role_membership rm
join pg_catalog.pg_roles member_role on member_role.oid = rm.member
join pg_catalog.pg_roles admin_role on admin_role.oid = rm.roleid
join predefined_admin_roles wanted on wanted.role_name = admin_role.rolname
where not member_role.rolsuper
  and member_role.rolname !~ '^pg_'
group by
  member_role.rolname,
  member_role.rolcanlogin,
  admin_role.rolname
order by
  risk_level desc,
  member_role.rolcanlogin desc,
  member_role.rolname asc,
  admin_role.rolname asc
