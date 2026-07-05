select
  slot_name,
  slot_type,
  coalesce(plugin, 'physical') as plugin,
  database,
  active,
  temporary,
  restart_lsn::text as restart_lsn,
  confirmed_flush_lsn::text as confirmed_flush_lsn,
  case
    when restart_lsn is null then null
    else pg_wal_lsn_diff(
      case
        when pg_is_in_recovery() then pg_last_wal_replay_lsn()
        else pg_current_wal_lsn()
      end,
      restart_lsn
    )::int8
  end as retained_wal_bytes,
  xmin::text as xmin,
  catalog_xmin::text as catalog_xmin,
  greatest(coalesce(age(xmin), 0), coalesce(age(catalog_xmin), 0))::int8 as xmin_age,
  coalesce(to_jsonb(s)->>'wal_status', '') as wal_status,
  coalesce(to_jsonb(s)->>'safe_wal_size', '') as safe_wal_size,
  coalesce(to_jsonb(s)->>'inactive_since', '') as inactive_since,
  coalesce(to_jsonb(s)->>'invalidation_reason', '') as invalidation_reason
from pg_replication_slots s
order by retained_wal_bytes desc nulls last, slot_name asc
