select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  st.schemaname,
  st.relname,
  st.seq_scan::int8 as seq_scan,
  st.seq_tup_read::int8 as seq_tup_read,
  st.idx_scan::int8 as idx_scan,
  st.idx_tup_fetch::int8 as idx_tup_fetch,
  st.n_tup_ins::int8 as n_tup_ins,
  st.n_tup_upd::int8 as n_tup_upd,
  st.n_tup_del::int8 as n_tup_del,
  (st.n_tup_ins + st.n_tup_upd + st.n_tup_del)::int8 as total_dml,
  st.n_tup_hot_upd::int8 as n_tup_hot_upd,
  st.n_live_tup::int8 as n_live_tup,
  st.n_dead_tup::int8 as n_dead_tup,
  st.vacuum_count::int8 as vacuum_count,
  st.autovacuum_count::int8 as autovacuum_count,
  st.analyze_count::int8 as analyze_count,
  st.autoanalyze_count::int8 as autoanalyze_count,
  st.last_vacuum,
  st.last_autovacuum,
  st.last_analyze,
  st.last_autoanalyze,
  pg_total_relation_size(st.relid)::int8 as total_relation_size_bytes
from pg_stat_all_tables st
join pg_class c on c.oid = st.relid
join pg_namespace n on n.oid = c.relnamespace
where n.nspname not in ('pg_catalog', 'information_schema')
  and n.nspname !~ '^pg_toast'
  and c.relkind in ('r', 'p', 'm')
order by total_dml desc nulls last, st.schemaname, st.relname
limit 200
