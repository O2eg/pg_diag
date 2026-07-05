select
  n.nspname as schemaname,
  c.relname as table_name,
  pg_total_relation_size(c.oid)::int8 as total_relation_size_bytes,
  coalesce(s.n_live_tup, 0)::int8 as n_live_tup,
  coalesce(s.n_dead_tup, 0)::int8 as n_dead_tup
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
left join pg_stat_all_tables s on s.relid = c.oid
where
  c.relkind in ('r', 'p')
  and n.nspname not in ('pg_catalog', 'pg_toast', 'information_schema')
  and not exists (
    select 1
    from pg_index i
    where i.indrelid = c.oid
      and (i.indisprimary or i.indisunique)
      and i.indisvalid
  )
order by total_relation_size_bytes desc, schemaname asc, table_name asc
limit 200
