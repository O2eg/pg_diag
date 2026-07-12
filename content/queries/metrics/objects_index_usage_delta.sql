select
  statement_timestamp() as snapshot_time,
  (select oid from pg_database where datname = current_database()) as datid,
  current_database() as datname,
  si.relid,
  si.indexrelid,
  si.schemaname,
  si.relname,
  si.indexrelname,
  (select stats_reset from pg_stat_database where datname = current_database())
    as database_stats_reset,
  si.idx_scan::int8 as idx_scan,
  si.idx_tup_read::int8 as idx_tup_read,
  si.idx_tup_fetch::int8 as idx_tup_fetch,
  io.idx_blks_read::int8 as idx_blks_read,
  io.idx_blks_hit::int8 as idx_blks_hit
from pg_stat_all_indexes si
join pg_class c on c.oid = si.indexrelid
join pg_namespace n on n.oid = c.relnamespace
join pg_statio_all_indexes io on io.indexrelid = si.indexrelid
where n.nspname not in ('pg_catalog', 'information_schema')
  and n.nspname !~ '^pg_toast'
  and (si.idx_scan <> 0)
order by si.idx_scan desc nulls last, si.schemaname, si.relname, si.indexrelname
limit 200
