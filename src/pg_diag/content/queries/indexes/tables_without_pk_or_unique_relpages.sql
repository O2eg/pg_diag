with recursive keyless_roots as (
  select
    c.oid,
    n.nspname as schemaname,
    c.relname as table_name,
    c.relkind,
    greatest(coalesce(c.relpages, 0), 0)::int8 as root_relpages
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  where c.relkind in ('r', 'p')
    and not c.relispartition
    and n.nspname not in ('pg_catalog', 'pg_toast', 'information_schema')
    and not exists (
      select 1
      from pg_index i
      where i.indrelid = c.oid
        and (i.indisprimary or i.indisunique)
        and i.indisvalid and i.indisready and i.indislive
        and i.indpred is null
    )
),
ordinary_roots as (
  select kr.*
  from keyless_roots kr
  where kr.relkind = 'r'
  order by kr.root_relpages desc, kr.schemaname, kr.table_name, kr.oid
  limit 200
),
partitioned_roots as (
  select kr.*
  from keyless_roots kr
  where kr.relkind = 'p'
  order by (
             select count(*)
             from pg_inherits i
             where i.inhparent = kr.oid
           ) desc,
           kr.schemaname, kr.table_name, kr.oid
  limit 200
),
selected_roots as (
  select * from ordinary_roots
  union all
  select * from partitioned_roots
),
root_coverage as (
  select
    (select count(*) from keyless_roots)::int8 as eligible_root_count,
    (select count(*) from selected_roots)::int8 as selected_root_count
),
relation_tree as (
  select sr.oid as root_oid, sr.oid as relation_oid
  from selected_roots sr
  union
  select rt.root_oid, i.inhrelid
  from relation_tree rt
  join pg_inherits i on i.inhparent = rt.relation_oid
),
tree_estimates as (
  select
    rt.root_oid,
    coalesce(
      sum(greatest(coalesce(c.relpages, 0), 0))
        filter (where c.relkind = 'r'),
      0
    )::int8 as estimated_table_relpages,
    coalesce(
      sum(coalesce(s.n_live_tup, 0))
        filter (where c.relkind = 'r'),
      0
    )::int8 as n_live_tup,
    coalesce(
      sum(coalesce(s.n_dead_tup, 0))
        filter (where c.relkind = 'r'),
      0
    )::int8 as n_dead_tup
  from relation_tree rt
  join pg_class c on c.oid = rt.relation_oid
  left join pg_stat_all_tables s on s.relid = rt.relation_oid
  group by rt.root_oid
),
candidates as (
  select
    kr.oid,
    kr.schemaname,
    kr.table_name,
    te.estimated_table_relpages,
    te.n_live_tup,
    te.n_dead_tup
  from selected_roots kr
  join tree_estimates te on te.root_oid = kr.oid
  order by te.estimated_table_relpages desc nulls last,
           kr.schemaname, kr.table_name, kr.oid
  limit 200
)
select
  c.oid as table_oid,
  c.schemaname,
  c.table_name,
  c.estimated_table_relpages,
  (
    c.estimated_table_relpages
    * current_setting('block_size')::int8
  )::int8 as estimated_table_size_bytes,
  c.n_live_tup,
  c.n_dead_tup,
  rc.eligible_root_count,
  rc.selected_root_count,
  (rc.selected_root_count < rc.eligible_root_count) as root_selection_truncated,
  case when c.n_live_tup >= 100000 then 'medium' else 'unknown' end as pg_diag_internal_severity,
  case
    when c.n_live_tup >= 100000 then 'Large durable-looking table has no valid non-partial primary or unique index.'
    else 'No valid non-partial primary or unique index; confirm whether the table is transient or intentionally keyless.'
  end as pg_diag_internal_reason
from candidates c
cross join root_coverage rc
order by c.estimated_table_relpages desc nulls last, c.schemaname, c.table_name, c.oid
