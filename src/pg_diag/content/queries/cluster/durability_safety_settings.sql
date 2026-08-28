with cluster_settings as (
  select s.name, s.setting, s.source, s.pending_restart
  from pg_catalog.pg_settings s
  where s.name in ('fsync', 'full_page_writes', 'synchronous_commit')
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
  where split_part(cfg.item, '=', 1) in ('fsync', 'full_page_writes', 'synchronous_commit')
  order by r.rolname nulls first, d.datname nulls first, cfg.item
  limit 200
)
select
  cs.name as setting_name,
  'cluster'::text as scope,
  cs.setting as current_value,
  cs.source,
  cs.pending_restart,
  case
    when cs.name = 'fsync' and cs.setting = 'off' then 'high'
    when cs.name = 'full_page_writes' and cs.setting = 'off' then 'high'
    when cs.name = 'synchronous_commit' and cs.setting = 'off' then 'medium'
    else 'ok'
  end as risk_level,
  case
    when cs.name = 'fsync' and cs.setting = 'off'
      then 'fsync=off can corrupt the whole cluster after a crash or power loss'
    when cs.name = 'full_page_writes' and cs.setting = 'off'
      then 'full_page_writes=off risks torn-page corruption after a crash unless the filesystem guarantees atomic 8kB writes'
    when cs.name = 'synchronous_commit' and cs.setting = 'off'
      then 'Cluster-wide synchronous_commit=off allows a bounded window of confirmed-transaction loss on crash; standby guarantees of other modes are assessed in the replication section'
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
    when o.name in ('fsync', 'full_page_writes') and lower(o.setting) in ('off', 'false', '0', 'no') then 'high'
    when o.name = 'synchronous_commit' and lower(o.setting) = 'off' then 'medium'
    else 'ok'
  end as risk_level,
  case
    when o.name in ('fsync', 'full_page_writes') and lower(o.setting) in ('off', 'false', '0', 'no')
      then 'A permanent override disables ' || o.name || ' for every new session in its scope'
    when o.name = 'synchronous_commit' and lower(o.setting) = 'off'
      then 'A permanent synchronous_commit=off override allows a bounded window of confirmed-transaction loss for every new session in its scope'
    else ''
  end as risk_reason
from overrides_bounded o

order by setting_name, scope
limit 210
