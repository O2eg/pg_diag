with triggers_bounded as (
  select t.oid, t.tgname, t.tgrelid
  from pg_catalog.pg_trigger t
  where not t.tgisinternal
    and t.tgenabled = 'D'
  order by t.tgrelid, t.tgname
  limit 1001
),
triggers_sample as (
  select * from triggers_bounded limit 1000
),
coverage as (
  select (select count(*) > 1000 from triggers_bounded) as result_truncated
)
select
  n.nspname as schema_name,
  c.relname as table_name,
  c.oid::int8 as table_oid,
  s.tgname as trigger_name,
  s.oid::int8 as trigger_oid,
  pg_catalog.pg_get_triggerdef(s.oid) as definition,
  coverage.result_truncated,
  'medium' as risk_level,
  'Trigger is disabled and does not fire; data the trigger was meant to maintain can silently diverge' as risk_reason
from triggers_sample s
join pg_catalog.pg_class c on c.oid = s.tgrelid
join pg_catalog.pg_namespace n on n.oid = c.relnamespace
cross join coverage
where n.nspname not in ('pg_catalog', 'information_schema')
order by schema_name, table_name, trigger_name
