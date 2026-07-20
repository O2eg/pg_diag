select
  statement_timestamp() as snapshot_time,
  (select oid from pg_database where datname = current_database()) as datid,
  current_database() as datname,
  st.relid,
  st.schemaname,
  st.relname,
  (select stats_reset from pg_stat_database where datname = current_database())
    as database_stats_reset,
  st.n_tup_ins::int8 as n_tup_ins,
  st.n_tup_upd::int8 as n_tup_upd,
  st.n_tup_del::int8 as n_tup_del,
  st.n_tup_hot_upd::int8 as n_tup_hot_upd,
  (st.n_tup_ins + st.n_tup_upd + st.n_tup_del)::int8 as total_dml
from pg_stat_all_tables st
join pg_class c on c.oid = st.relid
join pg_namespace n on n.oid = c.relnamespace
where n.nspname not in ('pg_catalog', 'information_schema')
  and n.nspname !~ '^pg_toast'
  and c.relkind in ('r', 'p', 'm')
order by (st.n_tup_ins + st.n_tup_upd + st.n_tup_del) desc nulls last, st.schemaname, st.relname
limit 200
