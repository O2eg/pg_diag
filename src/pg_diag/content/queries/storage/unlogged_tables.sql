with unlogged_bounded as (
  select c.oid, c.relname, c.relnamespace, c.relkind, c.relpages
  from pg_catalog.pg_class c
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where c.relpersistence = 'u'
    and c.relkind in ('r', 'S')
    and n.nspname not in ('pg_catalog', 'information_schema')
    and n.nspname not like 'pg_toast%'
  order by c.relpages desc, c.oid
  limit 501
),
unlogged_sample as (
  select * from unlogged_bounded limit 500
),
coverage as (
  select (select count(*) > 500 from unlogged_bounded) as result_truncated
)
select
  n.nspname as schema_name,
  s.relname as relation_name,
  case s.relkind when 'r' then 'table' when 'S' then 'sequence' else s.relkind::text end as relation_kind,
  pg_catalog.pg_total_relation_size(s.oid) as total_bytes,
  coverage.result_truncated,
  'medium' as risk_level,
  case s.relkind
    when 'r' then 'Unlogged table is emptied on crash recovery and is not replicated to standbys'
    else 'Unlogged sequence is reset on crash recovery and is not replicated to standbys'
  end as risk_reason
from unlogged_sample s
join pg_catalog.pg_namespace n on n.oid = s.relnamespace
cross join coverage
order by total_bytes desc, schema_name, relation_name
