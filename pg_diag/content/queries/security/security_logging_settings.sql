with checks(setting_name, expected, risk_level, risk_reason) as (
  values
    ('log_connections', 'on', 'medium', 'connection attempts are not logged'),
    ('log_disconnections', 'on', 'medium', 'session ends are not logged'),
    ('log_error_verbosity', 'verbose', 'medium', 'error logs may miss detailed context'),
    ('log_min_error_statement', 'error', 'medium', 'statements that raise errors may not be logged at the expected level'),
    ('log_statement', 'ddl/mod/all', 'medium', 'DDL statements may not be logged'),
    ('log_line_prefix', '%m %u %d %a %h', 'medium', 'log prefix may miss timestamp, user, database, app, or client address')
),
evaluated as (
  select
    c.setting_name,
    s.setting,
    s.source,
    s.pending_restart,
    c.expected,
    c.risk_level,
    c.risk_reason,
    case
      when c.setting_name in ('log_connections', 'log_disconnections') then s.setting = 'on'
      when c.setting_name = 'log_error_verbosity' then s.setting = 'verbose'
      when c.setting_name = 'log_min_error_statement' then s.setting in (
        'debug5', 'debug4', 'debug3', 'debug2', 'debug1',
        'info', 'notice', 'warning', 'error'
      )
      when c.setting_name = 'log_statement' then s.setting in ('ddl', 'mod', 'all')
      when c.setting_name = 'log_line_prefix' then
        strpos(s.setting, '%m') > 0
        and strpos(s.setting, '%u') > 0
        and strpos(s.setting, '%d') > 0
        and strpos(s.setting, '%a') > 0
        and strpos(s.setting, '%h') > 0
      else true
    end as is_ok
  from checks c
  join pg_catalog.pg_settings s on s.name = c.setting_name
)
select
  setting_name,
  setting as current_value,
  expected,
  source,
  pending_restart,
  risk_level,
  risk_reason
from evaluated
where not is_ok
order by setting_name asc
