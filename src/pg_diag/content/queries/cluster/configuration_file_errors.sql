with entries_bounded as (
  select f.seqno, f.name, f.setting, f.sourcefile, f.sourceline, f.applied, f.error
  from pg_catalog.pg_file_settings f
  where f.error is not null or not f.applied
  order by f.seqno
  limit 1001
),
entries_sample as (
  select * from entries_bounded limit 1000
),
coverage as (
  select (select count(*) > 1000 from entries_bounded) as result_truncated
),
classified as (
  select
    e.*,
    -- The file keeps a setting's "auto" sentinel (equal to boot_val, usually -1) and the server
    -- replaced it with a value computed at startup (pg_settings.source = 'override'). Every reload
    -- re-reads the sentinel, cannot apply it and reports the entry as an error: a reload artifact,
    -- not a misconfiguration (the same rows carry pending_restart in pending_restart_settings).
    coalesce(e.error is not null and s.source = 'override' and e.setting = s.boot_val, false) as auto_computed_artifact
  from entries_sample e
  left join pg_catalog.pg_settings s on s.name = e.name
)
select
  e.seqno::int8 as entry_order,
  e.name as setting_name,
  e.setting as file_value,
  e.sourcefile as source_file,
  e.sourceline::int8 as source_line,
  e.applied,
  e.error,
  e.auto_computed_artifact,
  coverage.result_truncated,
  case
    when e.error is not null and not e.auto_computed_artifact then 'high'
    else 'ok'
  end as risk_level,
  case
    when e.error is not null and e.auto_computed_artifact
      then 'The file keeps the auto value of a server-computed setting; the server reports it as not applied after every reload and no action is needed'
    when e.error is not null
      then 'The server cannot apply this configuration entry: ' || e.error
    else 'This entry is overridden by a later entry for the same parameter or by ALTER SYSTEM and has no effect'
  end as risk_reason
from classified e
cross join coverage
order by case when e.error is not null and not e.auto_computed_artifact then 0 else 1 end, e.seqno
