with summary as materialized (
  select buffers_unused::int8 as buffers_unused
  from public.pg_buffercache_summary()
), usage_counts as materialized (
  select usage_count::int4 as usage_count, buffers::int8 as buffers
  from public.pg_buffercache_usage_counts()
)
select
  statement_timestamp() as snapshot_time,
  ('usage count ' || usage_counts.usage_count)::text as usage_count_label,
  greatest(
    usage_counts.buffers
      - case when usage_counts.usage_count = 0 then summary.buffers_unused else 0 end,
    0
  )::int8 as buffers
from usage_counts
cross join summary
order by usage_counts.usage_count;
