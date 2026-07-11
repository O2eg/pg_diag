with candidates as (
  select
    i.indrelid,
    i.indexrelid,
    n.nspname as schemaname,
    tbl.relname as table_name,
    idx.relname as index_name,
    tbl.relpages as table_relpages,
    idx.relpages as index_relpages,
    s.idx_scan,
    s.idx_tup_read,
    s.idx_tup_fetch
  from pg_index i
  join pg_class idx on idx.oid = i.indexrelid and idx.relkind = 'i'
  join pg_class tbl on tbl.oid = i.indrelid and tbl.relkind = 'r'
  join pg_namespace n on n.oid = idx.relnamespace
  left join pg_stat_user_indexes s on s.indexrelid = idx.oid
  where n.nspname not in ('pg_catalog', 'pg_toast', 'information_schema')
    and tbl.relpages > 0
    and idx.relpages::numeric / tbl.relpages > 0.5
  order by idx.relpages::numeric / nullif(tbl.relpages, 0) desc,
           idx.relpages desc, n.nspname, tbl.relname, idx.relname, i.indexrelid
  limit 100
)
select
  c.indrelid as table_oid,
  c.indexrelid as index_oid,
  c.schemaname,
  c.table_name,
  c.index_name,
  db.stats_reset,
  pg_relation_size(c.indrelid)::int8 as table_size_bytes,
  pg_relation_size(c.indexrelid)::int8 as index_size_bytes,
  round(pg_relation_size(c.indexrelid)::numeric * 100 / nullif(pg_relation_size(c.indrelid), 0), 3) as index_to_table_pct,
  c.idx_scan,
  c.idx_tup_read,
  c.idx_tup_fetch
from candidates c
left join pg_stat_database db on db.datname = current_database()
where pg_relation_size(c.indrelid) > 0
order by index_to_table_pct desc nulls last, index_size_bytes desc, c.indexrelid
