select
  slot_name,
  slot_type,
  coalesce(plugin, 'physical') as plugin,
  database,
  active,
  active_pid,
  temporary,
  restart_lsn::text as restart_lsn,
  confirmed_flush_lsn::text as confirmed_flush_lsn,
  case
    when restart_lsn is null then null
    else pg_catalog.pg_wal_lsn_diff(
      case
        when pg_catalog.pg_is_in_recovery() then pg_catalog.pg_last_wal_replay_lsn()
        else pg_catalog.pg_current_wal_lsn()
      end,
      restart_lsn
    )::int8
  end as retained_wal_bytes,
  xmin::text as xmin,
  catalog_xmin::text as catalog_xmin,
  case
    when xmin is null and catalog_xmin is null then null
    else greatest(coalesce(pg_catalog.age(xmin), 0), coalesce(pg_catalog.age(catalog_xmin), 0))::int8
  end as xmin_age,
  null::text as wal_status,
  null::int8 as safe_wal_size_bytes,
  null::timestamptz as inactive_since,
  null::text as invalidation_reason,
  null::boolean as two_phase,
  null::boolean as failover,
  null::boolean as synced,
  null::boolean as conflicting,
  'ok'::text as pg_diag_internal_severity,
  ''::text as pg_diag_internal_reason
from pg_catalog.pg_replication_slots
order by retained_wal_bytes desc nulls last, slot_name asc
