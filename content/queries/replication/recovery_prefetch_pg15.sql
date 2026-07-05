with recovery_prefetch as (
  select
    case when pg_catalog.pg_is_in_recovery() then 'standby' else 'primary' end as server_role,
    stats_reset,
    extract(epoch from now() - stats_reset)::bigint as stats_age_seconds,
    prefetch,
    hit,
    skip_init,
    skip_new,
    skip_fpw,
    skip_rep,
    wal_distance,
    block_distance,
    io_depth,
    (
      coalesce(prefetch, 0)
      + coalesce(hit, 0)
      + coalesce(skip_init, 0)
      + coalesce(skip_new, 0)
      + coalesce(skip_fpw, 0)
      + coalesce(skip_rep, 0)
    ) as decisions_total
  from pg_catalog.pg_stat_recovery_prefetch
)
select
  server_role,
  stats_reset,
  stats_age_seconds,
  prefetch,
  hit,
  skip_init,
  skip_new,
  skip_fpw,
  skip_rep,
  decisions_total,
  round(100.0 * prefetch / nullif(decisions_total, 0), 2) as prefetch_pct,
  round(100.0 * hit / nullif(decisions_total, 0), 2) as hit_pct,
  wal_distance,
  block_distance,
  io_depth
from recovery_prefetch;
