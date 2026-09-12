with reset_events as (
  select
    'pg_stat_database'::text as source_view,
    'database'::text as object_type,
    coalesce(datname, '<shared>')::text as object_name,
    stats_reset as stat_reset_time
  from pg_stat_database
  union all
  select 'pg_stat_bgwriter', 'cluster', 'bgwriter', stats_reset
  from pg_stat_bgwriter
  union all
  select 'pg_stat_archiver', 'cluster', 'archiver', stats_reset
  from pg_stat_archiver
),
normalized as (
  select
    source_view,
    object_type,
    object_name,
    date_trunc('second', stat_reset_time) as stat_reset_time,
    case
      when stat_reset_time is null then null
      else extract(epoch from clock_timestamp() - date_trunc('second', stat_reset_time))::bigint
    end as seconds_since_reset
  from reset_events
),
epoch as (
  -- Shared (cluster-wide) views: a crash recovery discards all statistics and stamps every
  -- one of them at the same moment; a targeted pg_stat_reset_shared() stamps only its own.
  select
    pg_catalog.pg_postmaster_start_time() as postmaster_start,
    min(r.stat_reset_time) filter (where r.stat_reset_time > pg_catalog.pg_postmaster_start_time()) as first_shared_reset_after_start,
    max(r.stat_reset_time) filter (where r.stat_reset_time > pg_catalog.pg_postmaster_start_time()) as last_shared_reset_after_start,
    count(*) filter (where r.stat_reset_time > pg_catalog.pg_postmaster_start_time()) as shared_reset_after_start_count,
    count(*) filter (where r.stat_reset_time is not null) as shared_reported_count
  from reset_events r
  where r.object_type not in ('database', 'replication_slot', 'subscription')
),
classified as (
  select
    n.*,
    e.postmaster_start,
    e.last_shared_reset_after_start,
    -- every shared view carries the same post-start timestamp: the signature of a crash
    -- recovery (or of pg_stat_reset_shared() for all targets)
    e.shared_reported_count > 0
      and e.shared_reset_after_start_count = e.shared_reported_count
      and e.last_shared_reset_after_start - e.first_shared_reset_after_start <= interval '1 minute'
      as simultaneous_shared_reset
  from normalized n
  cross join epoch e
)
select
  current_database() as datname,
  c.source_view,
  c.object_type,
  c.object_name,
  c.stat_reset_time,
  case when c.stat_reset_time is null then 'not_reported' else 'reported' end as reset_status,
  c.seconds_since_reset,
  -- A view with its own timestamp accumulates since it. A row without one has accumulated at
  -- least since the later of the postmaster start and the last shared reset after it: a
  -- crash recovery discards every counter while pg_stat_database.stats_reset stays NULL, a
  -- targeted shared reset leaves the counters older, and statistics survive clean restarts.
  coalesce(c.stat_reset_time, greatest(c.postmaster_start, c.last_shared_reset_after_start)) as effective_window_start,
  c.postmaster_start,
  case
    when c.source_view = 'pg_stat_bgwriter' and c.simultaneous_shared_reset then 'medium'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when c.source_view = 'pg_stat_bgwriter' and c.simultaneous_shared_reset
      then 'Every shared statistics view was reset at the same moment after the postmaster started: a crash recovery (which also discards per-database and per-object counters while pg_stat_database.stats_reset stays NULL) or pg_stat_reset_shared() for all targets. Check server_log.server_lifecycle around this time; cumulative items report windows starting no earlier than it'
    when c.stat_reset_time > c.postmaster_start and c.simultaneous_shared_reset
      then 'part of the simultaneous shared statistics reset described on the pg_stat_bgwriter row'
    when c.stat_reset_time > c.postmaster_start
      then 'reset after the postmaster started by a targeted reset function; per-database and per-object counters are not affected by it'
    when c.stat_reset_time is null
      then 'never reset explicitly; counters have accumulated at least since effective_window_start (a crash recovery discards them without setting this timestamp)'
    else ''
  end as pg_diag_internal_reason
from classified c
order by c.seconds_since_reset asc nulls last, c.source_view asc, c.object_type asc, c.object_name asc
