with profile as (
  select
    pid,
    event_type,
    event,
    queryid,
    "count"::int8 as samples
  from pg_wait_sampling_profile
),
totals as (
  select
    sum(samples) filter (where event_type is distinct from 'Activity') as total_samples,
    sum(samples) filter (where event_type = 'Activity') as activity_samples
  from profile
)
select
  p.pid,
  p.event_type as wait_event_type,
  p.event as wait_event,
  p.queryid::text as query_id,
  ''::text as query,
  p.samples,
  (p.samples::numeric * 100 / nullif(t.total_samples, 0)) as sample_share_pct,
  coalesce(t.activity_samples, 0)::int8 as activity_samples_excluded
from profile p
cross join totals t
-- Activity events are the main loops of idle background processes (autovacuum launcher,
-- walwriter, io workers, ...); they dominate raw sample counts without describing waits.
where p.event_type is distinct from 'Activity'
order by p.samples desc nulls last, p.event_type, p.event
limit 100
