select
  n.nspname as schemaname,
  cr.relname as table_name,
  ci.relname as index_name,
  pg_relation_size(cr.oid)::int8 as table_size_bytes,
  pg_relation_size(ci.oid)::int8 as index_size_bytes,
  round(pg_relation_size(ci.oid)::numeric * 100 / nullif(pg_relation_size(cr.oid), 0), 3) as index_to_table_pct,
  s.idx_scan,
  s.idx_tup_read,
  s.idx_tup_fetch
from pg_index i
join pg_class ci on ci.oid = i.indexrelid and ci.relkind = 'i'
join pg_class cr on cr.oid = i.indrelid and cr.relkind in ('r', 'p')
join pg_namespace n on n.oid = ci.relnamespace
left join pg_stat_user_indexes s on s.indexrelid = ci.oid
where
  n.nspname not in ('pg_catalog', 'pg_toast', 'information_schema')
  and pg_relation_size(cr.oid) > 0
  and pg_relation_size(ci.oid)::numeric / pg_relation_size(cr.oid) > 0.5
order by index_to_table_pct desc, index_size_bytes desc
limit 100
