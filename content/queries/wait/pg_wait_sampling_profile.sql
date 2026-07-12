with profile as (
  select
    pid,
    event_type,
    event,
    queryid,
    "count"::int8 as samples,
    sum("count"::numeric) over () as total_samples
  from pg_wait_sampling_profile
)
select
  pid,
  event_type as wait_event_type,
  event as wait_event,
  queryid::text as query_id,
  ''::text as query,
  samples,
  (samples::numeric * 100 / nullif(total_samples, 0)) as sample_share_pct
from profile
order by samples desc nulls last, event_type, event
limit 100
