with constraints_bounded as (
  select c.oid, c.conname, c.contype, c.conrelid, c.confrelid
  from pg_catalog.pg_constraint c
  where not c.convalidated
    and c.contype in ('c', 'f')
  order by c.conrelid, c.conname
  limit 1001
),
constraints_sample as (
  select * from constraints_bounded limit 1000
),
coverage as (
  select (select count(*) > 1000 from constraints_bounded) as result_truncated
)
select
  n.nspname as schema_name,
  t.relname as table_name,
  s.conname as constraint_name,
  case s.contype when 'f' then 'FOREIGN KEY' when 'c' then 'CHECK' else s.contype::text end as constraint_type,
  fn.nspname as referenced_schema,
  ft.relname as referenced_table,
  pg_get_constraintdef(s.oid) as definition,
  coverage.result_truncated,
  'medium' as risk_level,
  'Constraint is NOT VALID: existing rows are unchecked and the planner cannot rely on it until VALIDATE CONSTRAINT succeeds' as risk_reason
from constraints_sample s
join pg_catalog.pg_class t on t.oid = s.conrelid
join pg_catalog.pg_namespace n on n.oid = t.relnamespace
left join pg_catalog.pg_class ft on ft.oid = s.confrelid
left join pg_catalog.pg_namespace fn on fn.oid = ft.relnamespace
cross join coverage
where n.nspname not in ('pg_catalog', 'information_schema')
order by schema_name, table_name, constraint_name
