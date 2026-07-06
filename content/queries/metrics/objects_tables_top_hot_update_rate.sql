select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  st.schemaname,
  st.relname,
  st.n_tup_hot_upd::int8 as n_tup_hot_upd
from pg_stat_all_tables st
join pg_class c on c.oid = st.relid
join pg_namespace n on n.oid = c.relnamespace
where n.nspname not in ('pg_catalog', 'information_schema')
  and n.nspname !~ '^pg_toast'
  and c.relkind in ('r', 'p', 'm')
order by st.n_tup_hot_upd desc nulls last, st.schemaname, st.relname
limit 200
