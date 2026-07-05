select
  p.datname,
  p.pid,
  p.relid::regclass::text as relation,
  p.index_relid::regclass::text as index_name,
  a.state,
  coalesce(a.wait_event_type || '.' || a.wait_event, '') as waiting,
  p.phase,
  p.current_locker_pid,
  p.lockers_total,
  p.lockers_done,
  round(p.lockers_done::numeric * 100 / nullif(p.lockers_total, 0), 3) as lockers_done_pct,
  p.blocks_total * current_setting('block_size')::int8 as total_bytes,
  p.blocks_done * current_setting('block_size')::int8 as done_bytes,
  round(p.blocks_done::numeric * 100 / nullif(p.blocks_total, 0), 3) as blocks_done_pct,
  p.tuples_total,
  p.tuples_done,
  round(p.tuples_done::numeric * 100 / nullif(p.tuples_total, 0), 3) as tuples_done_pct,
  p.partitions_total,
  p.partitions_done,
  round(p.partitions_done::numeric * 100 / nullif(p.partitions_total, 0), 3) as partitions_done_pct,
  extract(epoch from clock_timestamp() - a.xact_start)::numeric(20, 3) as xact_age_seconds,
  left(regexp_replace(coalesce(a.query, ''), '\s+', ' ', 'g'), 500) as query
from pg_stat_progress_create_index p
join pg_stat_activity a on p.pid = a.pid
where a.pid <> pg_backend_pid()
order by xact_age_seconds desc
