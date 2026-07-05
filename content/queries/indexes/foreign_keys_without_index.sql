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
  where
    con.contype = 'f'
    and n_source.nspname not in ('pg_catalog', 'pg_toast', 'information_schema')
)
select
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
  format(
    'CREATE INDEX ON %I.%I (%s)',
    fk.source_schema,
    fk.source_table,
    (
      select string_agg(quote_ident(a.attname), ', ' order by k.ord)
      from unnest(fk.conkey) with ordinality as k(attnum, ord)
      join pg_attribute a on a.attrelid = fk.conrelid and a.attnum = k.attnum
    )
  ) as suggested_index
from foreign_keys fk
where not exists (
  select 1
  from pg_index i
  where
    i.indrelid = fk.conrelid
    and i.indisvalid
    and i.indpred is null
    and (
      select array_agg(key.attnum order by key.ord)::smallint[]
      from unnest(i.indkey::smallint[]) with ordinality as key(attnum, ord)
      where key.ord <= array_length(fk.conkey, 1)
    ) = fk.conkey
)
order by source_schema, source_table, conname
limit 200
