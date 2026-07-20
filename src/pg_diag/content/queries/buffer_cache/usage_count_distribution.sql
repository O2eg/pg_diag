select
  statement_timestamp() as snapshot_time,
  ('usage count ' || usage_count)::text as usage_count_label,
  count(b.bufferid)::int8 as buffers
from generate_series(0, 5) usage_count
left join public.pg_buffercache b on b.usagecount = usage_count
group by usage_count
order by usage_count;
