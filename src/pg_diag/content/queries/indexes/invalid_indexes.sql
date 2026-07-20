with candidates as (
  select
    i.indexrelid,
    i.indrelid,
    n.nspname as schema_name,
    tbl.relname as table_name,
    idx.relname as index_name,
    idx.relpages,
    i.indisvalid,
    i.indisready,
    i.indislive,
    i.indisprimary,
    i.indisunique,
    con.conname as constraint_name
  from pg_index i
  join pg_class idx on idx.oid = i.indexrelid
  join pg_class tbl on tbl.oid = i.indrelid
  join pg_namespace n on n.oid = tbl.relnamespace
  left join pg_constraint con on con.conindid = i.indexrelid
  where (not i.indisvalid or not i.indisready or not i.indislive)
    and n.nspname not in ('pg_catalog', 'pg_toast', 'information_schema')
  order by idx.relpages desc nulls last, n.nspname, tbl.relname, idx.relname, i.indexrelid
  limit 100
)
select
  current_database() as datname,
  c.indrelid as table_oid,
  c.indexrelid as index_oid,
  c.schema_name,
  c.table_name,
  c.index_name,
  pg_get_indexdef(c.indexrelid) as index_definition,
  pg_relation_size(c.indexrelid)::int8 as index_size_bytes,
  c.indisvalid as is_valid,
  c.indisready as is_ready,
  c.indislive as is_live,
  c.indisprimary as is_pk,
  c.indisunique as is_unique,
  c.constraint_name,
  case when c.constraint_name is not null then 'high' else 'medium' end as pg_diag_internal_severity,
  case
    when c.constraint_name is not null then 'Invalid index backs a constraint; validate constraint enforcement and rebuild state immediately.'
    else 'Index is not valid, ready, or live and requires failed-DDL or rebuild review.'
  end as pg_diag_internal_reason
from candidates c
order by index_size_bytes desc nulls last, c.schema_name, c.table_name, c.index_name, c.indexrelid
