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
)
select
  current_database() as datname,
  source_view,
  object_type,
  object_name,
  stat_reset_time,
  case when stat_reset_time is null then 'not_reported' else 'reported' end as reset_status,
  seconds_since_reset
from normalized
order by seconds_since_reset asc nulls last, source_view asc, object_type asc, object_name asc
