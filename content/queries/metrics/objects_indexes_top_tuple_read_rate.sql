select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  si.relid,
  si.indexrelid,
  si.schemaname,
  si.relname,
  si.indexrelname,
  si.idx_tup_read::int8 as idx_tup_read
from pg_stat_all_indexes si
join pg_class c on c.oid = si.indexrelid
join pg_namespace n on n.oid = c.relnamespace
left join pg_statio_all_indexes io on io.indexrelid = si.indexrelid
where n.nspname not in ('pg_catalog', 'information_schema')
  and n.nspname !~ '^pg_toast'
  and (si.idx_tup_read <> 0)
order by si.idx_tup_read desc nulls last, si.schemaname, si.relname, si.indexrelname
limit 200
