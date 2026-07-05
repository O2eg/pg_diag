with index_data as (
  select
    *,
    string_to_array(indkey::text, ' ') as key_array,
    array_length(string_to_array(indkey::text, ' '), 1) as nkeys
  from pg_index
)
select
  i1.indrelid::regclass::text as table_name,
  i1.indexrelid::regclass::text as covering_index,
  i2.indexrelid::regclass::text as redundant_index,
  pg_relation_size(i2.indexrelid)::int8 as redundant_index_size_bytes,
  pg_get_indexdef(i1.indexrelid) as covering_index_def,
  pg_get_indexdef(i2.indexrelid) as redundant_index_def
from index_data i1
join index_data i2
  on i1.indrelid = i2.indrelid
  and i1.indexrelid <> i2.indexrelid
where
  regexp_replace(i1.indpred::text, 'location \d+', 'location', 'g') is not distinct from regexp_replace(i2.indpred::text, 'location \d+', 'location', 'g')
  and regexp_replace(i1.indexprs::text, 'location \d+', 'location', 'g') is not distinct from regexp_replace(i2.indexprs::text, 'location \d+', 'location', 'g')
  and (
    (i1.nkeys > i2.nkeys and not i2.indisunique)
    or (
      i1.nkeys = i2.nkeys
      and (
        (i1.indisunique and i2.indisunique and i1.indexrelid > i2.indexrelid)
        or (not i1.indisunique and not i2.indisunique and i1.indexrelid > i2.indexrelid)
        or (i1.indisunique and not i2.indisunique)
      )
    )
  )
  and i1.key_array[1:i2.nkeys] = i2.key_array
order by redundant_index_size_bytes desc, covering_index asc, redundant_index asc
limit 100
