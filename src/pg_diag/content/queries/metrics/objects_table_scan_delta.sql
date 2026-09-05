select
  statement_timestamp() as snapshot_time,
  (select oid from pg_database where datname = current_database()) as datid,
  current_database() as datname,
  st.relid,
  st.schemaname,
  st.relname,
  (select stats_reset from pg_stat_database where datname = current_database())
    as database_stats_reset,
  st.seq_scan::int8 as seq_scan,
  st.seq_tup_read::int8 as seq_tup_read,
  -- pg_stat_all_tables sums index scans; the sum is NULL when no indexes exist.
  coalesce(st.idx_scan, 0)::int8 as idx_scan,
  coalesce(st.idx_tup_fetch, 0)::int8 as idx_tup_fetch
from pg_stat_all_tables st
join pg_class c on c.oid = st.relid
join pg_namespace n on n.oid = c.relnamespace
where n.nspname not in ('pg_catalog', 'information_schema')
  and n.nspname !~ '^pg_toast'
  and c.relkind in ('r', 'p', 'm')
order by st.seq_tup_read desc nulls last, st.schemaname, st.relname
limit 200
