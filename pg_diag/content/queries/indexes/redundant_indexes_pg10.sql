with index_data as (
  select
    i.*,
    idx.relam,
    string_to_array(i.indkey::text, ' ') as key_array,
    string_to_array(i.indclass::text, ' ') as class_array,
    string_to_array(i.indcollation::text, ' ') as collation_array,
    string_to_array(i.indoption::text, ' ') as option_array
  from pg_index i
  join pg_class idx on idx.oid = i.indexrelid
  join pg_am am on am.oid = idx.relam and am.amname = 'btree'
  where i.indisvalid and i.indisready and i.indislive
)
select
  i1.indrelid as table_oid,
  i1.indexrelid as covering_index_oid,
  i2.indexrelid as redundant_index_oid,
  i1.indrelid::regclass::text as table_name,
  i1.indexrelid::regclass::text as covering_index,
  i2.indexrelid::regclass::text as redundant_index,
  pg_relation_size(i2.indexrelid)::int8 as redundant_index_size_bytes,
  pg_get_indexdef(i1.indexrelid) as covering_index_def,
  pg_get_indexdef(i2.indexrelid) as redundant_index_def,
  'unknown' as pg_diag_internal_severity,
  'The redundant index key is a structural left prefix; confirm plans, constraints, and workload before removal.' as pg_diag_internal_reason
from index_data i1
join index_data i2
  on i1.indrelid = i2.indrelid
 and i1.indexrelid <> i2.indexrelid
 and i1.relam = i2.relam
where i1.indnatts >= i2.indnatts
  and not i2.indisunique
  and i1.key_array[1:i2.indnatts] = i2.key_array[1:i2.indnatts]
  and i1.class_array[1:i2.indnatts] = i2.class_array[1:i2.indnatts]
  and i1.collation_array[1:i2.indnatts] = i2.collation_array[1:i2.indnatts]
  and i1.option_array[1:i2.indnatts] = i2.option_array[1:i2.indnatts]
  and i1.indpred is not distinct from i2.indpred
  and i1.indexprs is not distinct from i2.indexprs
  and not exists (select 1 from pg_constraint con where con.conindid = i2.indexrelid)
  and (i1.indnatts > i2.indnatts or i1.indexrelid > i2.indexrelid)
order by redundant_index_size_bytes desc, covering_index, redundant_index
limit 100
