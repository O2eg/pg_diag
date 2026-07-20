with physical as (
  select reltablespace, relfilenode, count(*)::int8 as cached_blocks
  from public.pg_buffercache
  where reldatabase = (select oid from pg_catalog.pg_database where datname = current_database())
    and relfilenode is not null
  group by reltablespace, relfilenode
), resolved as (
  select pg_catalog.pg_filenode_relation(reltablespace, relfilenode) as relation_oid,
         cached_blocks
  from physical
)
select
  statement_timestamp() as snapshot_time,
  coalesce(
    case c.relkind
      when 'r' then 'tables'
      when 'i' then 'indexes'
      when 'S' then 'sequences'
      when 't' then 'TOAST tables'
      when 'm' then 'materialized views'
      when 'p' then 'partitioned tables'
      when 'I' then 'partitioned indexes'
      else 'other (' || c.relkind::text || ')'
    end,
    'unresolved'
  ) as relation_kind,
  sum(r.cached_blocks)::int8 as cached_blocks
from resolved r
left join pg_catalog.pg_class c on c.oid = r.relation_oid
group by relation_kind
order by cached_blocks desc, relation_kind
limit 20;
