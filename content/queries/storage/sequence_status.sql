with default_value_sequences as (
  select s.seqrelid, c.oid
  from pg_catalog.pg_attribute a
  join pg_catalog.pg_attrdef ad on (ad.adrelid, ad.adnum) = (a.attrelid, a.attnum)
  join pg_catalog.pg_class c on a.attrelid = c.oid
  join pg_catalog.pg_sequence s
    on s.seqrelid = regexp_replace(
      pg_get_expr(ad.adbin, ad.adrelid),
      $re$^nextval\('(.+?)'::regclass\)$re$,
      $re$\1$re$
    )::regclass
  where pg_get_expr(ad.adbin, ad.adrelid) ~ '^nextval\('
),
dep_sequences as (
  select s.seqrelid, c.oid
  from pg_catalog.pg_sequence s
  join pg_catalog.pg_depend d on s.seqrelid = d.objid
  join pg_catalog.pg_class c on d.refobjid = c.oid
  union
  select seqrelid, oid from default_value_sequences
),
all_sequences as (
  select s.seqrelid as sequence_oid, ds.oid as table_oid
  from pg_catalog.pg_sequence s
  left join dep_sequences ds on s.seqrelid = ds.seqrelid
),
sequence_usage as (
  select
    format('%I.%I', s.schemaname, s.sequencename)::text as sequence_name,
    coalesce(s.last_value, s.min_value) as last_value,
    s.start_value,
    s.min_value,
    s.max_value,
    s.increment_by,
    s.cycle,
    ceil((s.max_value - s.min_value + 1)::numeric / nullif(abs(s.increment_by), 0)) as slots,
    ceil((coalesce(s.last_value, s.min_value) - s.min_value + 1)::numeric / nullif(abs(s.increment_by), 0)) as used,
    string_agg(a.table_oid::regclass::text, ', ' order by a.table_oid::regclass::text) as table_usage
  from pg_catalog.pg_sequences s
  join all_sequences a
    on format('%I.%I', s.schemaname, s.sequencename)::regclass = a.sequence_oid
  group by 1, 2, 3, 4, 5, 6, 7
)
select
  sequence_name,
  table_usage,
  last_value,
  start_value,
  min_value,
  max_value,
  increment_by,
  cycle,
  slots,
  used,
  round(used::numeric * 100 / nullif(slots, 0), 3) as percent,
  greatest(slots - used, 0) as remaining_values
from sequence_usage
order by percent desc nulls last, sequence_name asc
limit 200
