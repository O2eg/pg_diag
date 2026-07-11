select
  p.datid,
  p.datname,
  p.pid,
  p.relid,
  case when p.relid <> 0 then p.relid::regclass::text end as relation,
  a.state,
  coalesce(a.wait_event_type || '.' || a.wait_event, '') as waiting,
  p.command,
  p.type,
  p.bytes_total,
  p.bytes_processed as processed_bytes,
  round(p.bytes_processed::numeric * 100 / nullif(p.bytes_total, 0), 3) as processed_pct,
  p.tuples_processed,
  p.tuples_excluded,
  nullif(to_jsonb(p)->>'tuples_skipped', '')::int8 as tuples_skipped,
  extract(epoch from clock_timestamp() - a.query_start)::numeric(20, 3) as query_age_seconds,
  left(regexp_replace(coalesce(a.query, ''), '\s+', ' ', 'g'), 500) as query
from pg_catalog.pg_stat_progress_copy p
join pg_catalog.pg_stat_activity a on p.pid = a.pid
where p.datid = (select oid from pg_catalog.pg_database where datname = current_database())
  and a.pid <> pg_catalog.pg_backend_pid()
order by query_age_seconds desc
