with candidate_indexes as (
  select
    si.relid,
    si.indexrelid,
    si.schemaname,
    si.relname,
    si.indexrelname,
    si.idx_scan,
    si.idx_tup_read,
    si.idx_tup_fetch,
    c.relpages
  from pg_stat_all_indexes si
  join pg_class c on c.oid = si.indexrelid
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname not in ('pg_catalog', 'information_schema')
    and n.nspname !~ '^pg_toast'
    and si.idx_scan <> 0
  order by si.idx_scan desc nulls last, si.schemaname, si.relname, si.indexrelname, si.indexrelid
  limit 100
)
select
  statement_timestamp() as snapshot_time,
  current_database() as datname,
  si.relid,
  si.indexrelid,
  si.schemaname,
  si.relname,
  si.indexrelname,
  db.stats_reset,
  si.idx_scan::int8 as idx_scan,
  si.idx_tup_read::int8 as idx_tup_read,
  si.idx_tup_fetch::int8 as idx_tup_fetch,
  coalesce(io.idx_blks_read, 0)::int8 as idx_blks_read,
  coalesce(io.idx_blks_hit, 0)::int8 as idx_blks_hit,
  pg_relation_size(si.indexrelid)::int8 as index_size_bytes,
  si.relpages::int8 as index_relpages
from candidate_indexes si
left join pg_statio_all_indexes io on io.indexrelid = si.indexrelid
left join pg_stat_database db on db.datname = current_database()
order by si.idx_scan desc nulls last, si.schemaname, si.relname, si.indexrelname, si.indexrelid
