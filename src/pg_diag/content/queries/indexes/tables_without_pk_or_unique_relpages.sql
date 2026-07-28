with recursive ordinary_root_candidates as (
  select
    c.oid,
    c.relkind,
    greatest(coalesce(c.relpages, 0), 0)::int8 as root_relpages
  from pg_class c
  where c.relkind = 'r'
    and not c.relispartition
    and greatest(coalesce(c.relpages, 0), 0) > 0
    and c.relnamespace not in (
      select n.oid
      from pg_namespace n
      where n.nspname in ('pg_catalog', 'pg_toast', 'information_schema')
         or n.nspname like 'pg_toast%'
    )
  order by c.relpages desc, c.oid
  limit 10000
),
partitioned_root_candidates as (
  select
    c.oid,
    c.relkind,
    0::int8 as root_relpages
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  where c.relkind = 'p'
    and not c.relispartition
    and n.nspname not in ('pg_catalog', 'pg_toast', 'information_schema')
    and n.nspname not like 'pg_toast%'
  order by n.nspname, c.relname, c.oid
  limit 10000
),
root_candidates as (
  select * from ordinary_root_candidates
  union all
  select * from partitioned_root_candidates
),
keyless_roots as (
  select
    roots.oid,
    n.nspname as schemaname,
    c.relname as table_name,
    roots.relkind,
    roots.root_relpages
  from root_candidates roots
  join pg_class c on c.oid = roots.oid
  join pg_namespace n on n.oid = c.relnamespace
  where not exists (
    select 1
    from pg_index i
    where i.indrelid = roots.oid
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
  order by kr.schemaname, kr.table_name, kr.oid
  limit 200
),
selected_roots as (
  select * from ordinary_roots
  union all
  select * from partitioned_roots
),
root_coverage as (
  select
    (select count(*) from keyless_roots)::int8 as sampled_eligible_root_count,
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
bounded_relation_tree as (
  select *
  from relation_tree
  limit 3001
),
limited_relation_tree as (
  select *
  from bounded_relation_tree
  limit 3000
),
tree_coverage as (
  select (count(*) > 3000) as tree_truncated
  from bounded_relation_tree
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
  from limited_relation_tree rt
  join pg_class c on c.oid = rt.relation_oid
  left join pg_stat_all_tables s on s.relid = rt.relation_oid
  group by rt.root_oid
),
ranked_candidates as (
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
),
result_coverage as (
  select count(*)::int8 as ranked_candidate_count
  from ranked_candidates
),
candidates as (
  select *
  from ranked_candidates
  order by estimated_table_relpages desc nulls last,
           schemaname, table_name, oid
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
  rc.sampled_eligible_root_count,
  rc.selected_root_count,
  (rc.selected_root_count < rc.sampled_eligible_root_count) as root_selection_truncated,
  result_coverage.ranked_candidate_count,
  (result_coverage.ranked_candidate_count > 200) as result_truncated,
  tc.tree_truncated,
  case
    when tc.tree_truncated then 'unknown'
    when c.n_live_tup >= 100000 then 'medium'
    else 'unknown'
  end as pg_diag_internal_severity,
  case
    when tc.tree_truncated
      then 'Partition-tree sampling reached 3000 rows; row and size estimates are partial and are not used for severity.'
    when c.n_live_tup >= 100000 then 'Large durable-looking table has no valid non-partial primary or unique index.'
    else 'No valid non-partial primary or unique index; confirm whether the table is transient or intentionally keyless.'
  end as pg_diag_internal_reason
from candidates c
cross join root_coverage rc
cross join result_coverage
cross join tree_coverage tc
order by c.estimated_table_relpages desc nulls last, c.schemaname, c.table_name, c.oid
