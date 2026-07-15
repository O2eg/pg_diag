with fingerprints as (
  select
    i.indrelid,
    n.nspname as schemaname,
    tbl.relname as table_name,
    am.amname as access_method,
    i.indisunique,
    i.indisexclusion,
    i.indnatts as indnkeyatts,
    i.indkey::text as indkey,
    i.indclass::text as indclass,
    i.indcollation::text as indcollation,
    i.indoption::text as indoption,
    i.indpred::text as indpred,
    i.indexprs::text as indexprs,
    array_agg(idx.relname order by idx.relname, i.indexrelid) as index_names,
    array_agg(i.indexrelid order by idx.relname, i.indexrelid) as index_oids,
    sum(idx.relpages)::int8 as total_index_relpages,
    count(*)::int8 as index_count
  from pg_index i
  join pg_class idx on idx.oid = i.indexrelid
  join pg_class tbl on tbl.oid = i.indrelid
  join pg_namespace n on n.oid = tbl.relnamespace
  join pg_am am on am.oid = idx.relam
  where tbl.relkind in ('r', 'p')
    and i.indisvalid and i.indisready and i.indislive
    and n.nspname not in ('pg_catalog', 'pg_toast', 'information_schema')
  group by i.indrelid, n.nspname, tbl.relname, am.amname, i.indisunique,
           i.indisexclusion, i.indnatts, i.indkey::text, i.indclass::text,
           i.indcollation::text, i.indoption::text, i.indpred::text, i.indexprs::text
), candidates as (
  select *
  from fingerprints
  where index_count > 1
  order by total_index_relpages desc nulls last, schemaname, table_name, indrelid
  limit 100
)
select
  indrelid as table_oid,
  schemaname,
  table_name,
  access_method,
  indisunique as is_unique,
  indisexclusion as is_exclusion,
  index_count,
  sizes.total_index_size_bytes,
  index_oids,
  index_names,
  'medium' as pg_diag_internal_severity,
  'Indexes have matching structural fingerprints; dependencies and workload must still be checked before removal.' as pg_diag_internal_reason
from candidates
cross join lateral (
  select sum(pg_relation_size(index_oid))::int8 as total_index_size_bytes
  from unnest(index_oids) as index_oid
) sizes
order by sizes.total_index_size_bytes desc, schemaname, table_name, indrelid
