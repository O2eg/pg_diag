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
  case
    when xmin is null and catalog_xmin is null then null
    else greatest(coalesce(age(xmin), 0), coalesce(age(catalog_xmin), 0))::int8
  end as xmin_age,
  coalesce(to_jsonb(s)->>'wal_status', '') as wal_status,
  nullif(to_jsonb(s)->>'safe_wal_size', '')::int8 as safe_wal_size_bytes,
  nullif(to_jsonb(s)->>'inactive_since', '')::timestamptz as inactive_since,
  nullif(to_jsonb(s)->>'invalidation_reason', '') as invalidation_reason,
  nullif(to_jsonb(s)->>'two_phase', '')::boolean as two_phase,
  nullif(to_jsonb(s)->>'failover', '')::boolean as failover,
  nullif(to_jsonb(s)->>'synced', '')::boolean as synced,
  nullif(to_jsonb(s)->>'conflicting', '')::boolean as conflicting,
  case
    when nullif(to_jsonb(s)->>'invalidation_reason', '') is not null
      or coalesce(to_jsonb(s)->>'wal_status', '') = 'lost'
      then 'high'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when nullif(to_jsonb(s)->>'invalidation_reason', '') is not null
      then 'replication slot is invalidated'
    when coalesce(to_jsonb(s)->>'wal_status', '') = 'lost'
      then 'replication slot has lost required WAL'
    else ''
  end as pg_diag_internal_reason
from pg_replication_slots s
order by retained_wal_bytes desc nulls last, slot_name asc
