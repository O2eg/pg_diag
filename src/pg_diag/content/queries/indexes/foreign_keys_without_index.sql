with foreign_keys as (
  select
    con.oid,
    con.conname,
    con.conrelid,
    con.confrelid,
    con.conkey,
    con.confkey,
    n_source.nspname as source_schema,
    c_source.relname as source_table,
    n_target.nspname as target_schema,
    c_target.relname as target_table,
    pg_get_constraintdef(con.oid) as constraint_def
  from pg_constraint con
  join pg_class c_source on c_source.oid = con.conrelid
  join pg_namespace n_source on n_source.oid = c_source.relnamespace
  join pg_class c_target on c_target.oid = con.confrelid
  join pg_namespace n_target on n_target.oid = c_target.relnamespace
  where con.contype = 'f'
    and n_source.nspname not in ('pg_catalog', 'pg_toast', 'information_schema')
)
select
  fk.oid as constraint_oid,
  fk.conrelid as source_table_oid,
  fk.confrelid as target_table_oid,
  fk.source_schema,
  fk.source_table,
  fk.conname,
  (
    select string_agg(a.attname, ', ' order by k.ord)
    from unnest(fk.conkey) with ordinality as k(attnum, ord)
    join pg_attribute a on a.attrelid = fk.conrelid and a.attnum = k.attnum
  ) as source_columns,
  fk.target_schema,
  fk.target_table,
  (
    select string_agg(a.attname, ', ' order by k.ord)
    from unnest(fk.confkey) with ordinality as k(attnum, ord)
    join pg_attribute a on a.attrelid = fk.confrelid and a.attnum = k.attnum
  ) as target_columns,
  fk.constraint_def,
  coalesce(st.n_live_tup, 0)::int8 as source_n_live_tup,
  format(
    'CREATE INDEX ON %I.%I (%s)',
    fk.source_schema,
    fk.source_table,
    (
      select string_agg(quote_ident(a.attname), ', ' order by k.ord)
      from unnest(fk.conkey) with ordinality as k(attnum, ord)
      join pg_attribute a on a.attrelid = fk.conrelid and a.attnum = k.attnum
    )
  ) as suggested_index,
  case when coalesce(st.n_live_tup, 0) >= 100000 then 'medium' else 'unknown' end as pg_diag_internal_severity,
  case
    when coalesce(st.n_live_tup, 0) >= 100000 then 'Large referencing table has no valid full left-prefix index for this foreign key.'
    else 'No valid full left-prefix index; parent UPDATE/DELETE frequency determines whether an index is worthwhile.'
  end as pg_diag_internal_reason
from foreign_keys fk
left join pg_stat_all_tables st on st.relid = fk.conrelid
where not exists (
  select 1
  from pg_index i
  where i.indrelid = fk.conrelid
    and i.indisvalid and i.indisready and i.indislive
    and i.indpred is null
    and (
      select array_agg(key.attnum order by key.ord)::smallint[]
      from unnest(i.indkey::smallint[]) with ordinality as key(attnum, ord)
      where key.ord <= array_length(fk.conkey, 1)
    ) = fk.conkey
)
order by source_n_live_tup desc nulls last, source_schema, source_table, conname, constraint_oid
limit 200
