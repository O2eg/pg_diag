with cached as (
  select
    b.reldatabase,
    count(*)::int8 as cached_blocks
  from public.pg_buffercache b
  where b.relfilenode is not null
  group by b.reldatabase
),
per_database as (
  select 'shared catalogs'::text as database_name, coalesce(c.cached_blocks, 0)::int8 as cached_blocks
  from (select 0::oid as reldatabase) shared
  left join cached c on c.reldatabase = shared.reldatabase
  union all
  -- every database is listed, so a database without cached blocks is a zero, not a gap
  select d.datname::text, coalesce(c.cached_blocks, 0)::int8
  from pg_catalog.pg_database d
  left join cached c on c.reldatabase = d.oid
  union all
  select 'unknown database ' || c.reldatabase::text, c.cached_blocks
  from cached c
  where c.reldatabase <> 0
    and not exists (select 1 from pg_catalog.pg_database d where d.oid = c.reldatabase)
)
select
  statement_timestamp() as snapshot_time,
  database_name,
  cached_blocks
from per_database
order by cached_blocks desc, database_name
limit 100;
