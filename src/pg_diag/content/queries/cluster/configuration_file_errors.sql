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
)
select
  e.seqno::int8 as entry_order,
  e.name as setting_name,
  e.setting as file_value,
  e.sourcefile as source_file,
  e.sourceline::int8 as source_line,
  e.applied,
  e.error,
  coverage.result_truncated,
  case
    when e.error is not null then 'high'
    else 'ok'
  end as risk_level,
  case
    when e.error is not null
      then 'The server cannot apply this configuration entry: ' || e.error
    else 'This entry is overridden by a later entry for the same parameter or by ALTER SYSTEM and has no effect'
  end as risk_reason
from entries_sample e
cross join coverage
order by case when e.error is not null then 0 else 1 end, e.seqno
