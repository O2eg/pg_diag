select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  st.relid,
  st.schemaname,
  st.relname,
  st.n_tup_ins::int8 as n_tup_ins,
  st.n_tup_upd::int8 as n_tup_upd,
  st.n_tup_del::int8 as n_tup_del
from pg_stat_all_tables st
join pg_class c on c.oid = st.relid
join pg_namespace n on n.oid = c.relnamespace
where n.nspname not in ('pg_catalog', 'information_schema')
  and n.nspname !~ '^pg_toast'
  and c.relkind in ('r', 'p', 'm')
order by (st.n_tup_ins + st.n_tup_upd + st.n_tup_del) desc nulls last, st.schemaname, st.relname
limit 200
