with fk_indexes as materialized ( /* pgwatch_generated */
  select
    n.nspname as schema_name,
    ci.relname as index_name,
    cr.relname as table_name,
    (confrelid::regclass)::text as fk_table_ref,
    array_to_string(indclass, ', ') as opclasses
  from pg_index i
  join pg_class ci on ci.oid = i.indexrelid and ci.relkind = 'i'
  join pg_class cr on cr.oid = i.indrelid and cr.relkind = 'r'
  join pg_namespace n on n.oid = ci.relnamespace
  join pg_constraint cn on cn.conrelid = cr.oid
  left join pg_stat_all_indexes as si on si.indexrelid = i.indexrelid
  where
    contype = 'f'
    and i.indisunique is false
    and conkey is not null
    and ci.relpages > 5
    and si.idx_scan < 10
), table_scans as (
  select relid,
      tables.idx_scan + tables.seq_scan as all_scans,
      ( tables.n_tup_ins + tables.n_tup_upd + tables.n_tup_del ) as writes,
    pg_relation_size(relid) as table_size
      from pg_stat_all_tables as tables
      join pg_class c on c.oid = relid
      where c.relpages > 5
), indexes as (
  select
    i.indrelid,
    i.indexrelid,
    n.nspname as schema_name,
    cr.relname as table_name,
    ci.relname as index_name,
    si.idx_scan,
    pg_relation_size(i.indexrelid) as index_bytes,
    ci.relpages,
    (case when a.amname = 'btree' then true else false end) as idx_is_btree,
    array_to_string(i.indclass, ', ') as opclasses
  from pg_index i
    join pg_class ci on ci.oid = i.indexrelid and ci.relkind = 'i'
    join pg_class cr on cr.oid = i.indrelid and cr.relkind = 'r'
    join pg_namespace n on n.oid = ci.relnamespace
    join pg_am a on ci.relam = a.oid
    left join pg_stat_all_indexes as si on si.indexrelid = i.indexrelid
  where
    i.indisunique = false
    and i.indisvalid = true
    and ci.relpages > 5
), index_ratios as (
  select
    i.indexrelid as index_id,
    i.schema_name,
    i.table_name,
    i.index_name,
    idx_scan,
    all_scans,
    round(( case when all_scans = 0 then 0.0::numeric
      else idx_scan::numeric/all_scans * 100 end), 2) as index_scan_pct,
    writes,
    round((case when writes = 0 then idx_scan::numeric else idx_scan::numeric/writes end), 2)
      as scans_per_write,
    index_bytes as index_size_bytes,
    table_size as table_size_bytes,
    i.relpages,
    idx_is_btree,
    i.opclasses,
    (
      select count(1)
      from fk_indexes fi
      where fi.fk_table_ref = i.table_name
        and fi.schema_name = i.schema_name
        and fi.opclasses like (i.opclasses || '%')
    ) > 0 as supports_fk
  from indexes i
  join table_scans ts on ts.relid = i.indrelid
)
, ranked as (
  select
    row_number() over (
      order by index_size_bytes desc nulls last,
               schema_name, table_name, index_name
    ) as num,
    *
  from index_ratios
  where idx_scan = 0
    and idx_is_btree
)
select
  'Never Used Indexes' as reason,
  current_database() as datname,
  index_id,
  schema_name as schema_name,
  table_name as table_name,
  index_name as index_name,
  pg_get_indexdef(index_id) as index_definition,
  idx_scan,
  all_scans,
  index_scan_pct,
  writes,
  scans_per_write,
  index_size_bytes,
  table_size_bytes,
  relpages,
  idx_is_btree,
  opclasses as opclasses,
  supports_fk
from ranked
where num <= 100
union all
select
  'Never Used Indexes' as reason,
  current_database() as datname,
  0::oid as index_id,
  '$other$'::text as schema_name,
  '$other$'::text as table_name,
  '$other$'::text as index_name,
  '$other$'::text as index_definition,
  coalesce(sum(idx_scan), 0)::int8 as idx_scan,
  coalesce(sum(all_scans), 0)::int8 as all_scans,
  0::numeric as index_scan_pct,
  coalesce(sum(writes), 0)::int8 as writes,
  0::numeric as scans_per_write,
  coalesce(sum(index_size_bytes), 0)::int8 as index_size_bytes,
  coalesce(sum(table_size_bytes), 0)::int8 as table_size_bytes,
  coalesce(sum(relpages), 0)::int4 as relpages,
  true as idx_is_btree,
  '$other$'::text as opclasses,
  false as supports_fk
from ranked
where num > 100
group by ()
having count(*) > 0;
