with recursive publications_bounded as (
  select p.oid, p.pubname, p.puballtables, p.pubupdate, p.pubdelete
  from pg_catalog.pg_publication p
  order by p.pubname, p.oid
  limit 201
),
publications as (
  select * from publications_bounded limit 200
),
storage_table_roots_bounded as (
  select c.oid, c.relname, c.relnamespace, c.relkind, c.relreplident, c.relpersistence,
    greatest(coalesce(c.relpages, 0), 0)::int8 as relpages
  from pg_catalog.pg_class c
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where c.relkind in ('r', 'p')
    and greatest(coalesce(c.relpages, 0), 0) > 0
    and n.nspname not in ('pg_catalog', 'information_schema')
    and n.nspname not like 'pg_toast%'
  order by c.relpages desc, n.nspname, c.relname, c.oid
  limit 10001
),
storage_table_candidates as (
  select * from storage_table_roots_bounded limit 10000
),
named_table_roots_bounded as (
  select c.oid, c.relname, c.relnamespace, c.relkind, c.relreplident, c.relpersistence, 0::int8 as relpages
  from pg_catalog.pg_class c
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where c.relkind in ('r', 'p')
    and greatest(coalesce(c.relpages, 0), 0) = 0
    and n.nspname not in ('pg_catalog', 'information_schema')
    and n.nspname not like 'pg_toast%'
  order by n.nspname, c.relname, c.oid
  limit 10001
),
named_table_candidates as (
  select * from named_table_roots_bounded limit 10000
),
table_candidates as (
  select * from storage_table_candidates
  union all
  select * from named_table_candidates
),
explicit_bounded as (
  select pr.prpubid, pr.prrelid
  from pg_catalog.pg_publication_rel pr
  join publications p on p.oid = pr.prpubid
  order by pr.prpubid, pr.prrelid
  limit 10001
),
explicit_members as (
  select * from explicit_bounded limit 10000
),
partition_tree(pubid, root_oid, relid, depth) as (
  select e.prpubid, e.prrelid, e.prrelid, 0
  from explicit_members e
  union all
  select t.pubid, t.root_oid, i.inhrelid, t.depth + 1
  from partition_tree t
  join pg_catalog.pg_inherits i on i.inhparent = t.relid
  where t.depth < 8
),
partition_tree_bounded as (
  select * from partition_tree limit 20001
),
explicit_expanded as (
  select * from partition_tree_bounded limit 20000
),

published_bounded as (
  select p.oid as pubid, 'all tables'::text as publish_mode, null::oid as root_oid, t.*
  from publications p
  cross join table_candidates t
  where p.puballtables
  union all
  select x.pubid,
    case when x.depth = 0 then 'table'::text else 'partition'::text end,
    case when x.depth = 0 then null::oid else x.root_oid end,
    c.oid, c.relname, c.relnamespace, c.relkind, c.relreplident,
    c.relpersistence, greatest(coalesce(c.relpages, 0), 0)::int8
  from explicit_expanded x
  join pg_catalog.pg_class c on c.oid = x.relid

  limit 20001
),
published as (
  select * from published_bounded limit 20000
),
classified as (
  select
    pub.pubname,
    pub.pubupdate,
    pub.pubdelete,
    x.publish_mode,
    x.root_oid,
    x.oid,
    n.nspname,
    x.relname,
    x.relkind,
    x.relreplident,
    x.relpersistence,
    x.relpages,
    exists (
      select 1 from pg_catalog.pg_index i where i.indrelid = x.oid and i.indisprimary
    ) as has_primary_key,
    (
      select ic.relname
      from pg_catalog.pg_index i
      join pg_catalog.pg_class ic on ic.oid = i.indexrelid
      where i.indrelid = x.oid and i.indisreplident
      limit 1
    ) as replica_identity_index
  from published x
  join publications pub on pub.oid = x.pubid
  join pg_catalog.pg_namespace n on n.oid = x.relnamespace
  where x.relkind = 'r'
),
ranked_findings as (
  select
    c.pubname::text as publication_name,
    c.publish_mode,
    c.root_oid::regclass::text as published_root,
    c.nspname::text as schema_name,
    c.relname::text as table_name,
    c.oid::int8 as table_oid,
    case c.relreplident
      when 'd' then 'default'
      when 'n' then 'nothing'
      when 'f' then 'full'
      when 'i' then 'index'
      else c.relreplident::text
    end as replica_identity,
    c.has_primary_key,
    c.replica_identity_index::text as replica_identity_index,
    case c.relpersistence when 'u' then 'unlogged' when 't' then 'temporary' else 'permanent' end as persistence,
    c.pubupdate as publishes_update,
    c.pubdelete as publishes_delete,
    c.relpages,
    case
      when c.relpersistence = 'u' then 1
      when (c.relreplident = 'n' or (c.relreplident = 'd' and not c.has_primary_key))
        and (c.pubupdate or c.pubdelete) then 0
      when (c.relreplident = 'n' or (c.relreplident = 'd' and not c.has_primary_key)) then 2
      else 3
    end as risk_rank
  from classified c
  where c.relpersistence = 'u'
    or c.relreplident in ('n', 'f')
    or (c.relreplident = 'd' and not c.has_primary_key)
  order by 13, c.relpages desc, c.pubname, c.nspname, c.relname
  limit 3001
),
coverage as (
  select
    (
      (select count(*) > 10000 from storage_table_roots_bounded)
      or (select count(*) > 10000 from named_table_roots_bounded)
      or (select count(*) > 200 from publications_bounded)
    ) as candidate_sample_truncated,
    (
      (select count(*) > 10000 from explicit_bounded)
      or (select count(*) > 20000 from partition_tree_bounded)
      
      or (select count(*) > 20000 from published_bounded)
    ) as membership_sample_truncated,
    (select count(*) > 3000 from ranked_findings) as result_truncated
),
findings as (
  select * from ranked_findings limit 3000
),
combined as (
  select
    f.publication_name,
    f.publish_mode,
    f.published_root,
    f.schema_name,
    f.table_name,
    f.table_oid,
    f.replica_identity,
    f.has_primary_key,
    f.replica_identity_index,
    f.persistence,
    f.publishes_update,
    f.publishes_delete,
    f.relpages,
    cov.candidate_sample_truncated,
    cov.membership_sample_truncated,
    cov.result_truncated,
    f.risk_rank,
    case
      when f.risk_rank = 0 then 'high'
      when f.risk_rank = 1 then 'medium'
      else 'unknown'
    end as risk_level,
    case
      when f.risk_rank = 0
        then 'Published table has no usable replica identity: UPDATE and DELETE on the publisher fail until a primary key or REPLICA IDENTITY is defined'
      when f.risk_rank = 1
        then 'Unlogged table is included in a publication but its changes are never replicated'
      when f.replica_identity = 'full'
        then 'REPLICA IDENTITY FULL sends every column on UPDATE and DELETE; verify the WAL and subscriber cost'
      else 'Publication publishes inserts only; UPDATE and DELETE would fail if they were published'
    end as risk_reason
  from findings f
  cross join coverage cov
  union all
  select
    '[coverage]'::text, ''::text, null::text, ''::text, ''::text, null::int8, ''::text, false, null::text, ''::text,
    false, false, 0::int8,
    cov.candidate_sample_truncated, cov.membership_sample_truncated, cov.result_truncated,
    9, 'unknown'::text,
    'The bounded publication, table, partition, or membership sample was truncated; findings above are proven but the list is incomplete'::text
  from coverage cov
  where cov.candidate_sample_truncated or cov.membership_sample_truncated or cov.result_truncated
)
select
  publication_name,
  publish_mode,
  published_root,
  schema_name,
  table_name,
  table_oid,
  replica_identity,
  has_primary_key,
  replica_identity_index,
  persistence,
  publishes_update,
  publishes_delete,
  relpages,
  candidate_sample_truncated,
  membership_sample_truncated,
  result_truncated,
  risk_level,
  risk_reason
from combined
order by risk_rank, relpages desc, publication_name, schema_name, table_name
