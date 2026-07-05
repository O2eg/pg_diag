select
  pid,
  event_type as wait_event_type,
  event as wait_event,
  queryid::text as query_id,
  "count"::int8 as samples
from pg_wait_sampling_profile
order by "count" desc nulls last, event_type, event
limit 100
