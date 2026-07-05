with fk_indexes as materialized (
  select
    schemaname as schema_name,
    indexrelid,
    (indexrelid::regclass)::text as index_name,
    (relid::regclass)::text as table_name,
    (confrelid::regclass)::text as fk_table_ref,
    array_to_string(indclass, ', ') as opclasses
  from pg_stat_all_indexes
  join pg_index using (indexrelid)
  left join pg_constraint
    on array_to_string(indkey, ',') = array_to_string(conkey, ',')
      and schemaname = (connamespace::regnamespace)::text
      and conrelid = relid
      and contype = 'f'
  where idx_scan = 0
    and indisunique is false
    and conkey is not null
),
-- Find valid indexes that could be duplicates (same table, same columns)
valid_duplicates as (
  select
    inv.indexrelid as invalid_indexrelid,
    val.indexrelid as valid_indexrelid,
    (val.indexrelid::regclass)::text as valid_index_name,
    pg_get_indexdef(val.indexrelid) as valid_index_definition
  from pg_index inv
  join pg_index val on inv.indrelid = val.indrelid  -- same table
    and inv.indkey = val.indkey  -- same columns (in same order)
    and inv.indexrelid != val.indexrelid  -- different index
    and val.indisvalid = true  -- valid index
  where inv.indisvalid = false
),
data as (
  select
    pci.relname as index_name,
    pn.nspname as schema_name,
    pct.relname as table_name,
    coalesce(nullif(quote_ident(pn.nspname), 'public') || '.', '') || quote_ident(pct.relname) as relation_name,
    pg_get_indexdef(pidx.indexrelid) as index_definition,
    pg_relation_size(pidx.indexrelid) as index_size_bytes,
    -- Constraint info
    pidx.indisprimary as is_pk,
    pidx.indisunique as is_unique,
    con.conname as constraint_name,
    -- Table row estimate
    pct.reltuples::bigint as table_row_estimate,
    -- Valid duplicate check
    (vd.valid_indexrelid is not null) as has_valid_duplicate,
    vd.valid_index_name,
    vd.valid_index_definition,
    -- FK support check
    ((
      select count(1)
      from fk_indexes fi
      where fi.fk_table_ref = pct.relname
        and fi.opclasses like (array_to_string(pidx.indclass, ', ') || '%')
    ) > 0)::int as supports_fk
  from pg_index pidx
  join pg_class pci on pci.oid = pidx.indexrelid
  join pg_class pct on pct.oid = pidx.indrelid
  left join pg_namespace pn on pn.oid = pct.relnamespace
  left join pg_constraint con on con.conindid = pidx.indexrelid
  left join valid_duplicates vd on vd.invalid_indexrelid = pidx.indexrelid
  where pidx.indisvalid = false
),
ranked as (
  select
    row_number() over (
      order by index_size_bytes desc nulls last,
               schema_name, table_name, index_name
    ) as num,
    data.*
  from data
)
select
  current_database() as datname,
  num,
  index_name,
  schema_name,
  table_name,
  relation_name,
  index_definition,
  index_size_bytes,
  is_pk,
  is_unique,
  constraint_name,
  table_row_estimate,
  has_valid_duplicate,
  valid_index_name,
  valid_index_definition,
  supports_fk
from ranked
where num <= 100
union all
select
  current_database() as datname,
  0::bigint as num,
  '$other$'::text as index_name,
  '$other$'::text as schema_name,
  '$other$'::text as table_name,
  '$other$'::text as relation_name,
  '$other$'::text as index_definition,
  coalesce(sum(index_size_bytes), 0)::int8 as index_size_bytes,
  false as is_pk,
  false as is_unique,
  '$other$'::text as constraint_name,
  coalesce(sum(table_row_estimate), 0)::bigint as table_row_estimate,
  bool_or(has_valid_duplicate) as has_valid_duplicate,
  '$other$'::text as valid_index_name,
  '$other$'::text as valid_index_definition,
  coalesce(max(supports_fk), 0)::int as supports_fk
from ranked
where num > 100
group by ()
having count(*) > 0;
