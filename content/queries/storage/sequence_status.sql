with sequence_catalog as materialized (
  select
    s.seqrelid as sequence_oid,
    format('%I.%I', n.nspname, c.relname)::text as sequence_name,
    pg_catalog.format_type(s.seqtypid, null) as data_type,
    pg_catalog.pg_sequence_last_value(c.oid::regclass) as last_value,
    s.seqstart as start_value,
    s.seqmin as min_value,
    s.seqmax as max_value,
    s.seqincrement as increment_by,
    s.seqcache as cache_size,
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
  select distinct d.refobjid, ad.adrelid
  from pg_catalog.pg_depend d
  join pg_catalog.pg_attrdef ad on ad.oid = d.objid
  join sequence_catalog sc on sc.sequence_oid = d.refobjid
  where d.classid = 'pg_catalog.pg_attrdef'::regclass
    and d.refclassid = 'pg_catalog.pg_class'::regclass
    and d.deptype = 'n'
),
ranked_usage as (
  select
    r.sequence_oid,
    format('%I.%I', n.nspname, c.relname)::text as table_name,
    row_number() over (
      partition by r.sequence_oid order by n.nspname, c.relname
    ) as usage_rank
  from sequence_table_refs r
  join pg_catalog.pg_class c on c.oid = r.table_oid
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where c.relkind in ('r', 'p', 'f')
),
table_usage as (
  select
    sequence_oid,
    count(*) as table_usage_count,
    string_agg(table_name, ', ' order by table_name) filter (where usage_rank <= 20)
      as table_usage
  from ranked_usage
  group by sequence_oid
),
capacity as (
  select
    sc.*,
    coalesce(tu.table_usage_count, 0) as table_usage_count,
    case
      when coalesce(tu.table_usage_count, 0) > 20
        then tu.table_usage || format(', ... (%s total)', tu.table_usage_count)
      else tu.table_usage
    end as table_usage,
    floor((sc.max_value - sc.min_value)::numeric / nullif(abs(sc.increment_by), 0)) + 1
      as total_values,
    case
      when sc.last_value is null then null
      when sc.increment_by > 0 then
        floor((sc.last_value - sc.min_value)::numeric / sc.increment_by) + 1
      else
        floor((sc.max_value - sc.last_value)::numeric / abs(sc.increment_by)) + 1
    end as values_consumed
  from sequence_catalog sc
  left join table_usage tu on tu.sequence_oid = sc.sequence_oid
)
select
  sequence_oid,
  sequence_name,
  data_type,
  table_usage,
  table_usage_count,
  last_value,
  last_value is not null as value_visible,
  start_value,
  min_value,
  max_value,
  increment_by,
  cache_size,
  cycle,
  not cycle as exhaustion_applicable,
  total_values,
  values_consumed,
  case
    when cycle or values_consumed is null then null
    else round(values_consumed * 100 / nullif(total_values, 0), 3)
  end as percent,
  case
    when cycle or values_consumed is null then null
    else greatest(total_values - values_consumed, 0)
  end as remaining_values,
  case
    when cycle or values_consumed is null then 'ok'
    when values_consumed * 100 / nullif(total_values, 0) >= 99 then 'high'
    when values_consumed * 100 / nullif(total_values, 0) >= 90 then 'medium'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when cycle then ''
    when values_consumed is null then ''
    when values_consumed * 100 / nullif(total_values, 0) >= 99
      then 'non-cycling sequence consumed at least 99 percent of its directional range'
    when values_consumed * 100 / nullif(total_values, 0) >= 90
      then 'non-cycling sequence consumed at least 90 percent of its directional range'
    else ''
  end as pg_diag_internal_reason
from capacity
order by percent desc nulls last, sequence_name
limit 200
