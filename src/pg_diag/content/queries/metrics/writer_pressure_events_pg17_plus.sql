select
  statement_timestamp() as snapshot_time,
  'cluster'::text as scope,
  bgwriter.stats_reset as bgwriter_stats_reset,
  backends.io_stats_reset,
  bgwriter.maxwritten_clean::int8 as bgwriter_stops,
  backends.backend_fsyncs
from pg_catalog.pg_stat_bgwriter as bgwriter
cross join (
  select
    max(stats_reset) as io_stats_reset,
    sum(fsyncs)::int8 as backend_fsyncs
  from pg_catalog.pg_stat_io
  where object = 'relation'
    and context = 'normal'
    and backend_type <> 'checkpointer'
) as backends
