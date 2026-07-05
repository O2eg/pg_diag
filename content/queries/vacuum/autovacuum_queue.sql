with settings as (
  select
    (select setting::float8 from pg_settings where name = 'autovacuum_vacuum_threshold')        as default_threshold,
    (select setting::float8 from pg_settings where name = 'autovacuum_vacuum_scale_factor')    as default_scale_factor
),
tables as (
  select
    c.oid as relid,
    n.nspname as schemaname,
    c.relname as relname,
    -- pg_class.reltuples is -1 for tables that have never been ANALYZE'd
    -- (PG14+); clamping to 0 keeps the threshold and overdue factor
    -- well-defined for those tables.
    greatest(c.reltuples, 0)::float8 as reltuples,
    coalesce(
      (select option_value::float8 from pg_options_to_table(c.reloptions) where option_name = 'autovacuum_vacuum_threshold'),
      (select default_threshold from settings)
    ) as av_threshold,
    coalesce(
      (select option_value::float8 from pg_options_to_table(c.reloptions) where option_name = 'autovacuum_vacuum_scale_factor'),
      (select default_scale_factor from settings)
    ) as av_scale_factor
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  where c.relkind in ('r', 'm')
    and c.relpersistence <> 't'
    and not n.nspname like any (array[E'pg\\_%', 'information_schema'])
)
select /* pgwatch_generated */
  current_database() as datname,
  t.schemaname as schemaname,
  t.relname as relname,
  ut.n_dead_tup::int8 as n_dead_tup,
  ut.n_live_tup::int8 as n_live_tup,
  (t.av_threshold + t.av_scale_factor * t.reltuples)::int8 as autovacuum_threshold,
  case
    when (t.av_threshold + t.av_scale_factor * t.reltuples) > 0
    then ut.n_dead_tup::float8 / (t.av_threshold + t.av_scale_factor * t.reltuples)
    else 0
  end as autovacuum_overdue_factor
from tables t
join pg_stat_all_tables ut on ut.relid = t.relid
