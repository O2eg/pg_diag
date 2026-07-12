select
  statement_timestamp() as snapshot_time,
  (select oid from pg_database where datname = current_database()) as datid,
  current_database() as datname,
  st.relid,
  st.schemaname,
  st.relname,
  (select stats_reset from pg_stat_database where datname = current_database())
    as database_stats_reset,
  st.vacuum_count::int8 as vacuum_count,
  st.autovacuum_count::int8 as autovacuum_count,
  st.analyze_count::int8 as analyze_count,
  st.autoanalyze_count::int8 as autoanalyze_count,
  (st.vacuum_count + st.autovacuum_count + st.analyze_count + st.autoanalyze_count)::int8
    as maintenance_count,
  (to_jsonb(st)->>'total_vacuum_time')::numeric as vacuum_time_ms,
  (to_jsonb(st)->>'total_autovacuum_time')::numeric as autovacuum_time_ms,
  (to_jsonb(st)->>'total_analyze_time')::numeric as analyze_time_ms,
  (to_jsonb(st)->>'total_autoanalyze_time')::numeric as autoanalyze_time_ms,
  case
    when to_jsonb(st) ? 'total_vacuum_time' then
      (to_jsonb(st)->>'total_vacuum_time')::numeric
      + (to_jsonb(st)->>'total_autovacuum_time')::numeric
      + (to_jsonb(st)->>'total_analyze_time')::numeric
      + (to_jsonb(st)->>'total_autoanalyze_time')::numeric
  end as maintenance_time_ms
from pg_catalog.pg_stat_all_tables st
join pg_catalog.pg_class c on c.oid = st.relid
join pg_catalog.pg_namespace n on n.oid = c.relnamespace
where n.nspname not in ('pg_catalog', 'information_schema')
  and n.nspname !~ '^pg_toast'
  and c.relkind in ('r', 'p', 'm')
order by maintenance_count desc nulls last, st.schemaname, st.relname
limit 200
