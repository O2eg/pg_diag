select
  p.datname,
  p.pid,
  p.relid::regclass::text as relation,
  a.state,
  coalesce(a.wait_event_type || '.' || a.wait_event, '') as waiting,
  p.command,
  p.type,
  pg_relation_size(p.relid) as relation_size_bytes,
  p.bytes_total as source_total_bytes,
  p.bytes_processed as processed_bytes,
  round(p.bytes_processed::numeric * 100 / nullif(p.bytes_total, 0), 3) as processed_pct,
  p.tuples_processed,
  p.tuples_excluded,
  extract(epoch from clock_timestamp() - a.xact_start)::numeric(20, 3) as xact_age_seconds
from pg_stat_progress_copy p
join pg_stat_activity a on p.pid = a.pid
where
  a.pid <> pg_backend_pid()
  and not exists (
    select 1
    from pg_locks
    where relation = p.relid
      and mode = 'AccessExclusiveLock'
      and granted
  )
order by xact_age_seconds desc
