with candidates as (
  select
    c.oid,
    n.nspname as schemaname,
    c.relname as table_name,
    c.relpages,
    coalesce(s.n_live_tup, 0)::int8 as n_live_tup,
    coalesce(s.n_dead_tup, 0)::int8 as n_dead_tup
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  left join pg_stat_all_tables s on s.relid = c.oid
  where c.relkind in ('r', 'p')
    and not c.relispartition
    and n.nspname not in ('pg_catalog', 'pg_toast', 'information_schema')
    and not exists (
      select 1
      from pg_index i
      where i.indrelid = c.oid
        and (i.indisprimary or i.indisunique)
        and i.indisvalid and i.indisready and i.indislive
        and i.indpred is null
    )
  order by c.relpages desc nulls last, n.nspname, c.relname, c.oid
  limit 200
)
select
  c.oid as table_oid,
  c.schemaname,
  c.table_name,
  pg_total_relation_size(c.oid)::int8 as total_relation_size_bytes,
  c.n_live_tup,
  c.n_dead_tup,
  case when c.n_live_tup >= 100000 then 'medium' else 'unknown' end as pg_diag_internal_severity,
  case
    when c.n_live_tup >= 100000 then 'Large durable-looking table has no valid non-partial primary or unique index.'
    else 'No valid non-partial primary or unique index; confirm whether the table is transient or intentionally keyless.'
  end as pg_diag_internal_reason
from candidates c
order by total_relation_size_bytes desc nulls last, c.schemaname, c.table_name, c.oid
