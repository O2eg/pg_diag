with index_roots_bounded as (
  select
    idx.oid,
    idx.relam,
    greatest(coalesce(idx.relpages, 0), 0)::int8 as index_relpages,
    i.*
  from pg_class idx
  join pg_index i on i.indexrelid = idx.oid
  join pg_class tbl on tbl.oid = i.indrelid
  join pg_namespace n on n.oid = tbl.relnamespace
  join pg_am am on am.oid = idx.relam and am.amname = 'btree'
  where idx.relkind = 'i'
    and greatest(coalesce(idx.relpages, 0), 0) > 0
    and tbl.relkind in ('r', 'p')
    and i.indisvalid and i.indisready and i.indislive
    and n.nspname not in ('pg_catalog', 'pg_toast', 'information_schema')
    and n.nspname not like 'pg_toast%'
  order by idx.relpages desc, idx.oid
  limit 3001
),
index_roots as (
  select *
  from index_roots_bounded
  limit 3000
),
ranked_index_data as (
  select
    roots.*,
    row_number() over (
      partition by roots.indrelid
      order by roots.index_relpages desc, roots.indexrelid
    ) as table_index_rank,
    string_to_array(roots.indkey::text, ' ') as key_array,
    string_to_array(roots.indclass::text, ' ') as class_array,
    string_to_array(roots.indcollation::text, ' ') as collation_array,
    string_to_array(roots.indoption::text, ' ') as option_array
  from index_roots roots
),
index_data as (
  select *
  from ranked_index_data
  where table_index_rank <= 16
),
pair_roots_bounded as (
  select
    i1.indexrelid as covering_index_oid,
    i2.indexrelid as redundant_index_oid
  from index_data i1
  join index_data i2
    on i1.indrelid = i2.indrelid
   and i1.indexrelid <> i2.indexrelid
   and i1.relam = i2.relam
  where i1.indnatts >= i2.indnatts
    and not i2.indisunique
    and (i1.indnatts > i2.indnatts or i1.indexrelid > i2.indexrelid)
  order by i2.index_relpages desc, i2.indexrelid, i1.indexrelid
  limit 3001
),
pair_roots as (
  select *
  from pair_roots_bounded
  limit 3000
),
index_pairs as (
  select
    i1.indrelid,
    i1.indexrelid as covering_index_oid,
    i2.indexrelid as redundant_index_oid,
    i2.index_relpages as redundant_index_relpages
  from pair_roots roots
  join index_data i1 on i1.indexrelid = roots.covering_index_oid
  join index_data i2 on i2.indexrelid = roots.redundant_index_oid
  where i1.key_array[1:i2.indnatts] = i2.key_array[1:i2.indnatts]
    and i1.class_array[1:i2.indnatts] = i2.class_array[1:i2.indnatts]
    and i1.collation_array[1:i2.indnatts] = i2.collation_array[1:i2.indnatts]
    and i1.option_array[1:i2.indnatts] = i2.option_array[1:i2.indnatts]
    and i1.indpred is not distinct from i2.indpred
    and i1.indexprs is not distinct from i2.indexprs
    and not exists (select 1 from pg_constraint con where con.conindid = i2.indexrelid)
),
ranked_findings as (
  select *
  from index_pairs
  order by redundant_index_relpages desc, covering_index_oid, redundant_index_oid
  limit 101
),
coverage as (
  select
    (select count(*) > 3000 from index_roots_bounded) as root_sample_truncated,
    exists (
      select 1
      from ranked_index_data
      where table_index_rank > 16
    ) as table_index_sample_truncated,
    (select count(*) > 3000 from pair_roots_bounded) as pair_sample_truncated,
    (select count(*) > 100 from ranked_findings) as result_truncated
),
findings as (
  select *
  from ranked_findings
  limit 100
)
select
  findings.indrelid as table_oid,
  findings.covering_index_oid,
  findings.redundant_index_oid,
  findings.indrelid::regclass::text as table_name,
  findings.covering_index_oid::regclass::text as covering_index,
  findings.redundant_index_oid::regclass::text as redundant_index,
  (
    findings.redundant_index_relpages
    * current_setting('block_size')::int8
  )::int8 as estimated_redundant_index_size_bytes,
  pg_get_indexdef(findings.covering_index_oid) as covering_index_def,
  pg_get_indexdef(findings.redundant_index_oid) as redundant_index_def,
  coverage.root_sample_truncated,
  coverage.table_index_sample_truncated,
  coverage.pair_sample_truncated,
  coverage.result_truncated,
  'unknown' as pg_diag_internal_severity,
  case
    when coverage.root_sample_truncated
      or coverage.table_index_sample_truncated
      or coverage.pair_sample_truncated
      or coverage.result_truncated
      then 'The redundant-index result is based on truncated root, per-table, pair, or output samples; confirm plans, constraints, and workload before removal.'
    else 'The redundant index key is a structural left prefix; confirm plans, constraints, and workload before removal.'
  end as pg_diag_internal_reason
from findings
cross join coverage
union all
select
  null::oid,
  null::oid,
  null::oid,
  '[coverage]'::text,
  ''::text,
  ''::text,
  0::int8,
  ''::text,
  ''::text,
  coverage.root_sample_truncated,
  coverage.table_index_sample_truncated,
  coverage.pair_sample_truncated,
  coverage.result_truncated,
  'unknown'::text,
  'The bounded index root, per-table index, pair, or result sample was truncated; absence of redundant-index findings is not a clean result'::text
from coverage
where coverage.root_sample_truncated
   or coverage.table_index_sample_truncated
   or coverage.pair_sample_truncated
   or coverage.result_truncated
order by estimated_redundant_index_size_bytes desc, covering_index, redundant_index
