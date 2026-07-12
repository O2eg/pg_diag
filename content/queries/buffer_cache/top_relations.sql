with physical as (
  select reltablespace, relfilenode, count(*)::int8 as cached_blocks
  from public.pg_buffercache
  where reldatabase = (select oid from pg_catalog.pg_database where datname = current_database())
    and relfilenode is not null
  group by reltablespace, relfilenode
), resolved as (
  select
    coalesce(
      pg_catalog.pg_filenode_relation(reltablespace, relfilenode)::text,
      'unresolved:' || reltablespace::text || '/' || relfilenode::text
    ) as relation_name,
    cached_blocks
  from physical
), ranked as (
  select relation_name, sum(cached_blocks)::int8 as cached_blocks,
         row_number() over (order by sum(cached_blocks) desc, relation_name) as position
  from resolved
  group by relation_name
), bounded as (
  select relation_name, cached_blocks from ranked where position <= 30
  union all
  select 'Other', sum(cached_blocks)::int8 from ranked where position > 30
  having count(*) > 0
)
select statement_timestamp() as snapshot_time, relation_name, cached_blocks
from bounded
order by cached_blocks desc, relation_name
limit 31;
