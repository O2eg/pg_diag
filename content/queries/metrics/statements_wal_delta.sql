select
  statement_timestamp() as snapshot_time,
  d.datname,
  coalesce(r.rolname, s.userid::text) as rolname,
  s.queryid::text as query_id,
  s.wal_bytes::numeric as wal_bytes,
  s.wal_records::int8 as wal_records,
  s.wal_fpi::int8 as wal_fpi,
  left(coalesce(s.query, '<query text unavailable>'), 4000) as query
from pg_stat_statements s
join pg_database d on d.oid = s.dbid
left join pg_roles r on r.oid = s.userid
where d.datname = current_database()
order by s.wal_bytes desc nulls last
limit 50
