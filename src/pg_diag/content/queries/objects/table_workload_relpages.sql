with recursive workload_roots as (
  select
    st.relid,
    st.schemaname,
    st.relname,
    st.seq_scan,
    st.seq_tup_read,
    st.idx_scan,
    st.idx_tup_fetch,
    st.n_tup_ins,
    st.n_tup_upd,
    st.n_tup_del,
    st.n_tup_hot_upd,
    st.n_live_tup,
    st.n_dead_tup,
    st.vacuum_count,
    st.autovacuum_count,
    st.analyze_count,
    st.autoanalyze_count,
    st.last_vacuum,
    st.last_autovacuum,
    st.last_analyze,
    st.last_autoanalyze
  from pg_stat_user_tables st
  order by (st.n_tup_ins + st.n_tup_upd + st.n_tup_del) desc nulls last,
           st.schemaname, st.relname, st.relid
  limit 200
),
candidates as (
  select wr.*
  from workload_roots wr
  join pg_class c on c.oid = wr.relid
  where c.relkind in ('r', 'p', 'm')
),
relation_tree as (
  select c.relid as root_oid, c.relid as relation_oid
  from candidates c
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
page_estimates as (
  select
    rt.root_oid,
    coalesce(
      sum(greatest(coalesce(c.relpages, 0), 0))
        filter (where c.relkind in ('r', 'm')),
      0
    )::int8 as estimated_table_relpages
  from limited_relation_tree rt
  join pg_class c on c.oid = rt.relation_oid
  group by rt.root_oid
)
select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  c.relid,
  c.schemaname,
  c.relname,
  db.stats_reset,
  c.seq_scan::int8 as seq_scan,
  c.seq_tup_read::int8 as seq_tup_read,
  c.idx_scan::int8 as idx_scan,
  c.idx_tup_fetch::int8 as idx_tup_fetch,
  c.n_tup_ins::int8 as n_tup_ins,
  c.n_tup_upd::int8 as n_tup_upd,
  c.n_tup_del::int8 as n_tup_del,
  (c.n_tup_ins + c.n_tup_upd + c.n_tup_del)::int8 as total_dml,
  c.n_tup_hot_upd::int8 as n_tup_hot_upd,
  c.n_live_tup::int8 as n_live_tup,
  c.n_dead_tup::int8 as n_dead_tup,
  c.vacuum_count::int8 as vacuum_count,
  c.autovacuum_count::int8 as autovacuum_count,
  c.analyze_count::int8 as analyze_count,
  c.autoanalyze_count::int8 as autoanalyze_count,
  c.last_vacuum,
  c.last_autovacuum,
  c.last_analyze,
  c.last_autoanalyze,
  pe.estimated_table_relpages,
  (
    pe.estimated_table_relpages
    * current_setting('block_size')::int8
  )::int8 as estimated_table_size_bytes,
  tc.tree_truncated,
  case
    when c.seq_scan >= 1000 and c.seq_tup_read >= 10000000 then 'medium'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when c.seq_scan >= 1000 and c.seq_tup_read >= 10000000
      then 'High cumulative sequential-scan volume; validate workload and index selectivity before changing indexes.'
    else null
  end as pg_diag_internal_reason
from candidates c
join page_estimates pe on pe.root_oid = c.relid
cross join tree_coverage tc
left join pg_stat_database db on db.datname = current_database()
order by total_dml desc nulls last, c.schemaname, c.relname, c.relid
