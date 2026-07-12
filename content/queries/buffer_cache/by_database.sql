select
  statement_timestamp() as snapshot_time,
  case
    when b.reldatabase = 0 then 'shared catalogs'
    else coalesce(d.datname, 'unknown database ' || b.reldatabase::text)
  end as database_name,
  count(*)::int8 as cached_blocks
from public.pg_buffercache b
left join pg_catalog.pg_database d on d.oid = b.reldatabase
where b.relfilenode is not null
group by b.reldatabase, d.datname
order by cached_blocks desc, database_name
limit 100;
