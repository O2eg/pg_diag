with index_roots as (
  select
    idx.oid,
    idx.relname as index_name,
    greatest(coalesce(idx.relpages, 0), 0)::int8 as index_relpages,
    idx.relam,
    i.*,
    tbl.relname as table_name,
    n.nspname as schemaname
  from pg_class idx
  join pg_index i on i.indexrelid = idx.oid
  join pg_class tbl on tbl.oid = i.indrelid
  join pg_namespace n on n.oid = tbl.relnamespace
  where idx.relkind = 'i'
    and greatest(coalesce(idx.relpages, 0), 0) > 0
    and tbl.relkind in ('r', 'p')
    and i.indisvalid and i.indisready and i.indislive
    and n.nspname not in ('pg_catalog', 'pg_toast', 'information_schema')
    and n.nspname not like 'pg_toast%'
  order by idx.relpages desc, n.nspname, tbl.relname, idx.relname, idx.oid
  limit 3000
),
candidate_indexes as (
  select roots.*
  from index_roots roots
  order by roots.index_relpages desc, roots.schemaname, roots.table_name,
           roots.index_name, roots.indexrelid
),
fingerprints as (
  select
    i.indrelid,
    i.schemaname,
    i.table_name,
    am.amname as access_method,
    i.indisunique,
    i.indisexclusion,
    i.indnkeyatts,
    i.indkey::text as indkey,
    i.indclass::text as indclass,
    i.indcollation::text as indcollation,
    i.indoption::text as indoption,
    i.indpred::text as indpred,
    i.indexprs::text as indexprs,
    array_agg(i.index_name order by i.index_name, i.indexrelid) as index_names,
    array_agg(i.indexrelid order by i.index_name, i.indexrelid) as index_oids,
    sum(i.index_relpages)::int8 as estimated_total_index_relpages,
    count(*)::int8 as sampled_index_count
  from candidate_indexes i
  join pg_am am on am.oid = i.relam
  group by i.indrelid, i.schemaname, i.table_name, am.amname, i.indisunique,
           i.indisexclusion, i.indnkeyatts, i.indkey::text, i.indclass::text,
           i.indcollation::text, i.indoption::text, i.indpred::text, i.indexprs::text
), candidates as (
  select *
  from fingerprints
  where sampled_index_count > 1
  order by estimated_total_index_relpages desc nulls last, schemaname, table_name, indrelid
  limit 100
)
select
  indrelid as table_oid,
  schemaname,
  table_name,
  access_method,
  indisunique as is_unique,
  indisexclusion as is_exclusion,
  sampled_index_count,
  (
    estimated_total_index_relpages
    * current_setting('block_size')::int8
  )::int8 as estimated_total_index_size_bytes,
  index_oids,
  index_names,
  'medium' as pg_diag_internal_severity,
  'Indexes in the bounded large-index sample have matching structural fingerprints; dependencies and workload must still be checked before removal.' as pg_diag_internal_reason
from candidates
order by estimated_total_index_size_bytes desc, schemaname, table_name, indrelid
