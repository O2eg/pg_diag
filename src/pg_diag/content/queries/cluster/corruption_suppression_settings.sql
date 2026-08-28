with cluster_settings as (
  select s.name, s.setting, s.source, s.pending_restart
  from pg_catalog.pg_settings s
  where s.name in ('ignore_checksum_failure', 'zero_damaged_pages', 'ignore_invalid_pages')
),
overrides_bounded as (
  select
    split_part(cfg.item, '=', 1) as name,
    substring(cfg.item from strpos(cfg.item, '=') + 1) as setting,
    r.rolname,
    d.datname
  from pg_catalog.pg_db_role_setting drs
  cross join lateral unnest(drs.setconfig) as cfg(item)
  left join pg_catalog.pg_roles r on r.oid = drs.setrole
  left join pg_catalog.pg_database d on d.oid = drs.setdatabase
  where split_part(cfg.item, '=', 1)
    in ('ignore_checksum_failure', 'zero_damaged_pages', 'ignore_invalid_pages')
  order by r.rolname nulls first, d.datname nulls first, cfg.item
  limit 200
)
select
  cs.name as setting_name,
  'cluster'::text as scope,
  cs.setting as current_value,
  cs.source,
  cs.pending_restart,
  case when cs.setting = 'on' then 'high' else 'ok' end as risk_level,
  case
    when cs.setting <> 'on' then ''
    when cs.name = 'ignore_checksum_failure'
      then 'Checksum failures are reported but ignored; corrupted pages keep being used and corruption can spread'
    when cs.name = 'zero_damaged_pages'
      then 'Damaged pages are silently zeroed on read; this destroys data instead of surfacing corruption'
    when cs.name = 'ignore_invalid_pages'
      then 'Invalid pages found during recovery are ignored; the cluster can start with lost or inconsistent data'
    else ''
  end as risk_reason
from cluster_settings cs

union all

select
  o.name as setting_name,
  concat_ws(
    ' ',
    case when o.rolname is not null then 'role ' || o.rolname end,
    case when o.datname is not null then 'database ' || o.datname end
  ) as scope,
  o.setting as current_value,
  'pg_db_role_setting'::text as source,
  null::boolean as pending_restart,
  case
    when lower(o.setting) in ('on', 'true', '1', 'yes') then 'high'
    else 'ok'
  end as risk_level,
  case
    when lower(o.setting) in ('on', 'true', '1', 'yes')
      then 'A permanent override enables ' || o.name
        || ' for every new session in its scope; corruption evidence is silently suppressed there'
    else ''
  end as risk_reason
from overrides_bounded o

order by setting_name, scope
limit 210
