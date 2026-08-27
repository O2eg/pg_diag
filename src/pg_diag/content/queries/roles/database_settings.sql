with settings_bounded as (
  select
    s.setrole,
    s.setdatabase,
    cfg.entry as setting_entry,
    cfg.ord
  from pg_catalog.pg_db_role_setting s
  cross join lateral unnest(s.setconfig) with ordinality cfg(entry, ord)
  order by s.setrole, s.setdatabase, cfg.ord
  limit 5001
),
settings_sample as (
  select * from settings_bounded limit 5000
),
coverage as (
  select (select count(*) > 5000 from settings_bounded) as result_truncated
)
select
  case
    when s.setrole = 0 then 'database'
    when s.setdatabase = 0 then 'role'
    else 'role in database'
  end as scope,
  coalesce(r.rolname::text, '[all roles]') as role_name,
  coalesce(d.datname::text, '[all databases]') as database_name,
  (s.setdatabase = 0 or d.datname = current_database()) as applies_to_current_database,
  split_part(s.setting_entry, '=', 1) as setting_name,
  substr(s.setting_entry, strpos(s.setting_entry, '=') + 1) as setting_value,
  ps.context as setting_context,
  ps.category as setting_category,
  coverage.result_truncated,
  case when coverage.result_truncated then 'unknown' else 'ok' end as pg_diag_internal_severity,
  case
    when coverage.result_truncated
      then 'More than 5000 role or database setting entries exist; the list is partial'
    else ''
  end as pg_diag_internal_reason
from settings_sample s
left join pg_catalog.pg_roles r on r.oid = s.setrole
left join pg_catalog.pg_database d on d.oid = s.setdatabase
left join pg_catalog.pg_settings ps on ps.name = split_part(s.setting_entry, '=', 1)
cross join coverage
order by scope, role_name, database_name, setting_name
