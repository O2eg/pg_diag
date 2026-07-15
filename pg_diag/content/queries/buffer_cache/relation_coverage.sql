with physical as (
  select reltablespace, relfilenode, count(*)::int8 as cached_blocks
  from public.pg_buffercache
  where reldatabase = (select oid from pg_catalog.pg_database where datname = current_database())
    and relfilenode is not null
  group by reltablespace, relfilenode
), resolved as (
  select pg_catalog.pg_filenode_relation(reltablespace, relfilenode) as relation_oid,
         sum(cached_blocks)::int8 as cached_blocks
  from physical
  group by pg_catalog.pg_filenode_relation(reltablespace, relfilenode)
), sized as (
  select
    r.relation_oid::text as relation_name,
    r.cached_blocks,
    greatest(
      ceil(pg_catalog.pg_relation_size(r.relation_oid)::numeric /
           pg_catalog.current_setting('block_size')::numeric),
      1
    ) as relation_blocks
  from resolved r
  join pg_catalog.pg_class c on c.oid = r.relation_oid
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where r.relation_oid is not null
    and n.nspname !~ '^pg_'
    and n.nspname <> 'information_schema'
)
select
  statement_timestamp() as snapshot_time,
  relation_name,
  least(100.0, cached_blocks::numeric * 100.0 / relation_blocks)::float8 as coverage_pct
from sized
order by cached_blocks desc, relation_name
limit 30;
