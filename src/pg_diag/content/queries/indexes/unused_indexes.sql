with candidates as (
  select
    i.indrelid,
    i.indexrelid,
    n.nspname as schema_name,
    tbl.relname as table_name,
    idx.relname as index_name,
    idx.relpages,
    coalesce(si.idx_scan, 0)::int8 as idx_scan,
    (coalesce(ts.n_tup_ins, 0) + coalesce(ts.n_tup_upd, 0) + coalesce(ts.n_tup_del, 0))::int8 as writes,
    exists (
      select 1
      from pg_constraint fk
      where fk.contype = 'f'
        and fk.conrelid = i.indrelid
        and (
          select array_agg(k.attnum order by k.ord)::smallint[]
          from unnest(i.indkey::smallint[]) with ordinality as k(attnum, ord)
          where k.ord <= array_length(fk.conkey, 1)
        ) = fk.conkey
    ) as supports_fk
  from pg_index i
  join pg_class idx on idx.oid = i.indexrelid
  join pg_class tbl on tbl.oid = i.indrelid
  join pg_namespace n on n.oid = tbl.relnamespace
  join pg_am am on am.oid = idx.relam
  left join pg_stat_all_indexes si on si.indexrelid = i.indexrelid
  left join pg_stat_all_tables ts on ts.relid = i.indrelid
  where not i.indisunique
    and i.indisvalid and i.indisready and i.indislive
    and am.amname = 'btree'
    and idx.relpages > 5
    and coalesce(si.idx_scan, 0) = 0
    and n.nspname not in ('pg_catalog', 'pg_toast', 'information_schema')
  order by idx.relpages desc nulls last, n.nspname, tbl.relname, idx.relname, i.indexrelid
  limit 100
)
select
  current_database() as datname,
  c.indrelid as table_oid,
  c.indexrelid as index_oid,
  c.schema_name,
  c.table_name,
  c.index_name,
  pg_get_indexdef(c.indexrelid) as index_definition,
  db.stats_reset,
  c.idx_scan,
  c.writes,
  pg_relation_size(c.indexrelid)::int8 as index_size_bytes,
  pg_relation_size(c.indrelid)::int8 as table_size_bytes,
  c.relpages,
  c.supports_fk,
  case
    when not c.supports_fk
      and db.stats_reset <= statement_timestamp() - interval '30 days'
      and c.writes >= 100000 then 'medium'
    else 'unknown'
  end as pg_diag_internal_severity,
  case
    when c.supports_fk then 'Zero scans do not make a foreign-key support index removable.'
    when db.stats_reset is null then 'Statistics reset time is unavailable; zero scans have no known observation window.'
    when db.stats_reset > statement_timestamp() - interval '30 days' then 'Statistics are younger than 30 days; zero scans are insufficient evidence.'
    when c.writes >= 100000 then 'No scans over at least 30 days while the table accumulated substantial writes; review as a removal candidate.'
    else 'No scans observed, but the workload evidence is not strong enough for automatic severity.'
  end as pg_diag_internal_reason
from candidates c
left join pg_stat_database db on db.datname = current_database()
order by index_size_bytes desc nulls last, c.schema_name, c.table_name, c.index_name, c.indexrelid
