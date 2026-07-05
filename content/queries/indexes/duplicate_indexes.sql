with index_fingerprints as (
  select
    i.indrelid,
    n.nspname as schemaname,
    c.relname as table_name,
    i.indkey::text as indkey,
    i.indclass::text as indclass,
    i.indcollation::text as indcollation,
    i.indoption::text as indoption,
    i.indpred::text as indpred,
    i.indexprs::text as indexprs,
    array_agg(ic.relname order by ic.relname) as index_names,
    sum(pg_relation_size(i.indexrelid))::int8 as total_index_size_bytes,
    count(*)::int8 as index_count
  from pg_index i
  join pg_class ic on ic.oid = i.indexrelid
  join pg_class c on c.oid = i.indrelid
  join pg_namespace n on n.oid = c.relnamespace
  where
    c.relkind in ('r', 'p')
    and n.nspname not in ('pg_catalog', 'pg_toast', 'information_schema')
  group by 1, 2, 3, 4, 5, 6, 7, 8, 9
)
select
  schemaname,
  table_name,
  index_count,
  total_index_size_bytes,
  index_names
from index_fingerprints
where index_count > 1
order by total_index_size_bytes desc, schemaname asc, table_name asc
limit 100
