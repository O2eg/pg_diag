with sequence_catalog as materialized (
  select
    s.seqrelid as sequence_oid,
    format('%I.%I', n.nspname, c.relname)::text as sequence_name,
    pg_catalog.pg_sequence_last_value(c.oid::regclass) as last_value,
    s.seqstart as start_value,
    s.seqmin as min_value,
    s.seqmax as max_value,
    s.seqincrement as increment_by,
    s.seqcycle as cycle
  from pg_catalog.pg_sequence s
  join pg_catalog.pg_class c on c.oid = s.seqrelid
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where c.relkind = 'S'
    and not pg_catalog.pg_is_other_temp_schema(n.oid)
),
sequence_table_refs as materialized (
  select distinct d.objid as sequence_oid, d.refobjid as table_oid
  from pg_catalog.pg_depend d
  join sequence_catalog sc on sc.sequence_oid = d.objid
  where d.classid = 'pg_catalog.pg_class'::regclass
    and d.refclassid = 'pg_catalog.pg_class'::regclass
    and d.deptype in ('a', 'i')
    and d.refobjsubid > 0

  union

  select distinct d.refobjid as sequence_oid, ad.adrelid as table_oid
  from pg_catalog.pg_depend d
  join pg_catalog.pg_attrdef ad on ad.oid = d.objid
  join sequence_catalog sc on sc.sequence_oid = d.refobjid
  where d.classid = 'pg_catalog.pg_attrdef'::regclass
    and d.refclassid = 'pg_catalog.pg_class'::regclass
    and d.deptype = 'n'
),
sequence_table_names as materialized (
  select
    r.sequence_oid,
    format('%I.%I', n.nspname, c.relname)::text as table_name
  from sequence_table_refs r
  join pg_catalog.pg_class c on c.oid = r.table_oid
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where c.relkind in ('r', 'p', 'f')
),
ranked_table_usage as (
  select
    sequence_oid,
    table_name,
    row_number() over (
      partition by sequence_oid
      order by table_name
    ) as usage_rank
  from sequence_table_names
),
sequence_table_usage as materialized (
  select
    sequence_oid,
    count(*) as table_usage_count,
    string_agg(table_name, ', ' order by table_name) filter (where usage_rank <= 20) as table_usage
  from ranked_table_usage
  group by sequence_oid
),
sequence_usage as (
  select
    sc.sequence_name,
    coalesce(tu.table_usage_count, 0) as table_usage_count,
    coalesce(sc.last_value, sc.min_value) as last_value,
    sc.start_value,
    sc.min_value,
    sc.max_value,
    sc.increment_by,
    sc.cycle,
    ceil((sc.max_value - sc.min_value + 1)::numeric / nullif(abs(sc.increment_by), 0)) as slots,
    ceil((coalesce(sc.last_value, sc.min_value) - sc.min_value + 1)::numeric / nullif(abs(sc.increment_by), 0)) as used,
    case
      when coalesce(tu.table_usage_count, 0) > 20
      then tu.table_usage || format(', ... (%s total)', tu.table_usage_count)
      else tu.table_usage
    end as table_usage
  from sequence_catalog sc
  left join sequence_table_usage tu
    on tu.sequence_oid = sc.sequence_oid
)
select
  sequence_name,
  table_usage,
  table_usage_count,
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
