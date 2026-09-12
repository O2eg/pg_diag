with senders as (
  select
    r.*,
    -- a walsender streaming for a logical slot is a logical replication sender
    coalesce(slot.slot_type::text, 'physical') as sender_kind,
    slot.slot_name::text as slot_name,
    case
      when pg_catalog.pg_is_in_recovery() then pg_catalog.pg_last_wal_replay_lsn()
      else pg_catalog.pg_current_wal_lsn()
    end as local_wal_lsn
  from pg_catalog.pg_stat_replication r
  left join pg_catalog.pg_replication_slots slot on slot.active_pid = r.pid
)
select
  case when pg_catalog.pg_is_in_recovery() then 'cascading standby' else 'primary' end
    as server_role,
  sender_kind,
  slot_name,
  pid,
  usesysid,
  usename,
  application_name,
  client_addr::text as client_addr,
  client_hostname,
  client_port,
  backend_start,
  backend_xmin::text as backend_xmin,
  state,
  sync_state,
  sync_priority,
  local_wal_lsn::text as current_wal_lsn,
  sent_lsn::text as sent_lsn,
  write_lsn::text as write_lsn,
  flush_lsn::text as flush_lsn,
  replay_lsn::text as replay_lsn,
  pg_catalog.pg_wal_lsn_diff(local_wal_lsn, sent_lsn)::int8
    as current_to_sent_lag_bytes,
  pg_catalog.pg_wal_lsn_diff(sent_lsn, write_lsn)::int8 as sent_to_write_lag_bytes,
  pg_catalog.pg_wal_lsn_diff(write_lsn, flush_lsn)::int8 as write_to_flush_lag_bytes,
  pg_catalog.pg_wal_lsn_diff(flush_lsn, replay_lsn)::int8 as flush_to_replay_lag_bytes,
  pg_catalog.pg_wal_lsn_diff(local_wal_lsn, replay_lsn)::int8
    as current_to_replay_lag_bytes,
  extract(epoch from write_lag)::numeric as write_lag_seconds,
  extract(epoch from flush_lag)::numeric as flush_lag_seconds,
  extract(epoch from replay_lag)::numeric as replay_lag_seconds,
  null::timestamptz as reply_time,
  null::numeric as seconds_since_reply,
  case when state = 'streaming' then 'ok' else 'medium' end
    as pg_diag_internal_severity,
  case
    when state <> 'streaming' then 'WAL sender is not in streaming state'
    when sender_kind = 'logical' then 'logical replication sender: write/flush/replay positions are subscriber confirmations, not standby replay'
    else ''
  end as pg_diag_internal_reason
from senders
order by sender_kind asc, current_to_replay_lag_bytes desc nulls last, application_name, pid
