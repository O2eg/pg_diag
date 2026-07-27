with recursive candidate_indexes as (
  select
    si.relid,
    si.indexrelid,
    si.schemaname,
    si.relname,
    si.indexrelname,
    si.idx_scan,
    si.idx_tup_read,
    si.idx_tup_fetch
  from pg_stat_all_indexes si
  join pg_class c on c.oid = si.indexrelid
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname not in ('pg_catalog', 'information_schema')
    and n.nspname !~ '^pg_toast'
    and si.idx_scan <> 0
  order by si.idx_scan desc nulls last, si.schemaname, si.relname, si.indexrelname, si.indexrelid
  limit 100
),
index_tree as (
  select ci.indexrelid as root_oid, ci.indexrelid as index_oid
  from candidate_indexes ci
  union
  select it.root_oid, i.inhrelid
  from index_tree it
  join pg_inherits i on i.inhparent = it.index_oid
),
page_estimates as (
  select
    it.root_oid,
    coalesce(
      sum(greatest(coalesce(c.relpages, 0), 0))
        filter (where c.relkind = 'i'),
      0
    )::int8 as estimated_index_relpages
  from index_tree it
  join pg_class c on c.oid = it.index_oid
  group by it.root_oid
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
  pe.estimated_index_relpages,
  (
    pe.estimated_index_relpages
    * current_setting('block_size')::int8
  )::int8 as estimated_index_size_bytes
from candidate_indexes si
join page_estimates pe on pe.root_oid = si.indexrelid
left join pg_statio_all_indexes io on io.indexrelid = si.indexrelid
left join pg_stat_database db on db.datname = current_database()
order by si.idx_scan desc nulls last, si.schemaname, si.relname, si.indexrelname, si.indexrelid
