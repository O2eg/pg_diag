with settings as (
  select
    btrim(current_setting('synchronous_standby_names')) as names_setting,
    current_setting('synchronous_commit') as synchronous_commit
),
parsed as (
  select
    names_setting,
    synchronous_commit,
    case
      when names_setting = '' then 'none'
      when names_setting ~ '(?i)^any\s+\d+\s*\(' then 'ANY'
      else 'FIRST'
    end as sync_method,
    case
      when names_setting = '' then 0
      else coalesce(substring(names_setting from '(?i)^(?:first|any)\s+(\d+)')::int, 1)
    end as required_sync_count,
    coalesce(
      substring(names_setting from '(?i)^(?:first|any)\s+\d+\s*\((.*)\)\s*$'),
      names_setting
    ) as names_text,
    (synchronous_commit not in ('off', 'local')) as commit_waits_for_standby
  from settings
),
configured_names_bounded as (
  select
    p.sync_method,
    p.required_sync_count,
    p.synchronous_commit,
    p.commit_waits_for_standby,
    trim(both '"' from btrim(n.entry)) as standby_name,
    n.ord
  from parsed p
  cross join lateral regexp_split_to_table(p.names_text, ',') with ordinality as n(entry, ord)
  where p.sync_method <> 'none'
    and btrim(n.entry) <> ''
  order by n.ord
  limit 101
),
configured_names as (
  select * from configured_names_bounded limit 100
),
senders_bounded as (
  select
    r.pid,
    r.application_name,
    r.client_addr::text as client_addr,
    r.state,
    r.sync_state,
    r.sync_priority,
    pg_catalog.pg_wal_lsn_diff(
      case
        when pg_catalog.pg_is_in_recovery() then pg_catalog.pg_last_wal_replay_lsn()
        else pg_catalog.pg_current_wal_lsn()
      end,
      r.replay_lsn
    )::int8 as replay_lag_bytes,
    extract(epoch from r.replay_lag)::float8 as replay_lag_seconds
  from pg_catalog.pg_stat_replication r
  order by r.sync_priority, r.application_name, r.pid
  limit 1001
),
senders as (
  select * from senders_bounded limit 1000
),
sender_totals as (
  select
    count(*)::int8 as sender_count,
    count(*) filter (where sync_state = 'sync')::int8 as sync_sender_count,
    count(*) filter (where sync_state = 'quorum')::int8 as quorum_sender_count,
    count(*) filter (where sync_state = 'potential')::int8 as potential_sender_count
  from senders
),
waiters as (
  select count(*)::int8 as syncrep_waiting_sessions
  from pg_catalog.pg_stat_activity a
  where a.wait_event_type = 'IPC'
    and a.wait_event = 'SyncRep'
),
quorum as (
  select
    p.sync_method,
    p.required_sync_count,
    p.commit_waits_for_standby,
    case
      when p.sync_method = 'none' then true
      when p.sync_method = 'ANY' then t.quorum_sender_count >= p.required_sync_count
      else t.sync_sender_count >= p.required_sync_count
    end as quorum_satisfied
  from parsed p
  cross join sender_totals t
),
coverage as (
  select
    (select count(*) > 100 from configured_names_bounded) as names_truncated,
    (select count(*) > 1000 from senders_bounded) as senders_truncated
),
name_rows as (
  select
    c.standby_name,
    c.ord::int8 as configured_position,
    c.sync_method,
    c.required_sync_count::int8 as required_sync_count,
    c.synchronous_commit,
    c.commit_waits_for_standby,
    (
      select count(*)::int8 from senders s
      where c.standby_name = '*' or lower(s.application_name) = lower(c.standby_name)
    ) as matching_sender_count,
    (
      select count(*)::int8 from senders s
      where (c.standby_name = '*' or lower(s.application_name) = lower(c.standby_name))
        and s.sync_state in ('sync', 'quorum')
    ) as matching_sync_sender_count,
    (
      select
        case
          when bool_or(s.sync_state = 'sync') then 'sync'
          when bool_or(s.sync_state = 'quorum') then 'quorum'
          when bool_or(s.sync_state = 'potential') then 'potential'
          when count(*) > 0 then 'async'
          else 'absent'
        end
      from senders s
      where c.standby_name = '*' or lower(s.application_name) = lower(c.standby_name)
    ) as best_sync_state,
    (
      select max(s.replay_lag_bytes) from senders s
      where c.standby_name = '*' or lower(s.application_name) = lower(c.standby_name)
    )::int8 as max_replay_lag_bytes,
    (
      select max(s.replay_lag_seconds) from senders s
      where c.standby_name = '*' or lower(s.application_name) = lower(c.standby_name)
    )::float8 as max_replay_lag_seconds
  from configured_names c
),
findings as (
  select
    n.standby_name,
    n.configured_position,
    n.sync_method,
    n.required_sync_count,
    n.synchronous_commit,
    n.commit_waits_for_standby,
    n.matching_sender_count,
    n.matching_sync_sender_count,
    n.best_sync_state,
    n.max_replay_lag_bytes,
    n.max_replay_lag_seconds,
    t.sender_count,
    t.sync_sender_count,
    t.quorum_sender_count,
    t.potential_sender_count,
    q.quorum_satisfied,
    w.syncrep_waiting_sessions,
    cov.names_truncated,
    cov.senders_truncated,
    case
      when cov.names_truncated or cov.senders_truncated then 'unknown'
      when not q.quorum_satisfied and n.commit_waits_for_standby then 'high'
      when not q.quorum_satisfied then 'medium'
      when n.matching_sender_count = 0 then 'medium'
      when not n.commit_waits_for_standby then 'unknown'
      else 'ok'
    end as risk_level,
    case
      when cov.names_truncated or cov.senders_truncated
        then 'Configured standby names or WAL senders were truncated; the synchronous status is partial'
      when not q.quorum_satisfied and n.commit_waits_for_standby
        then 'Synchronous quorum is not satisfied: commits wait for '
          || n.required_sync_count::text || ' synchronous standby(s) but only '
          || (case when n.sync_method = 'ANY' then t.quorum_sender_count else t.sync_sender_count end)::text
          || ' candidate(s) are connected'
      when not q.quorum_satisfied
        then 'Synchronous quorum is not satisfied, but synchronous_commit=' || n.synchronous_commit
          || ' lets commits proceed without standby confirmation'
      when n.matching_sender_count = 0
        then 'Configured standby is not connected; the quorum is satisfied by other candidates'
      when not n.commit_waits_for_standby
        then 'synchronous_standby_names is configured but synchronous_commit=' || n.synchronous_commit
          || ' does not wait for standby confirmation at the server level'
      else ''
    end as risk_reason
  from name_rows n
  cross join sender_totals t
  cross join quorum q
  cross join waiters w
  cross join coverage cov
)
select * from findings
union all
select
  '[none]'::text,
  null::int8,
  'none'::text,
  0::int8,
  p.synchronous_commit,
  p.commit_waits_for_standby,
  t.sender_count,
  0::int8,
  case when t.sender_count > 0 then 'async' else 'absent' end,
  null::int8,
  null::float8,
  t.sender_count,
  t.sync_sender_count,
  t.quorum_sender_count,
  t.potential_sender_count,
  true,
  w.syncrep_waiting_sessions,
  cov.names_truncated,
  cov.senders_truncated,
  'ok'::text,
  'synchronous_standby_names is empty; replication is asynchronous'::text
from parsed p
cross join sender_totals t
cross join waiters w
cross join coverage cov
where p.sync_method = 'none'
order by configured_position nulls last, standby_name
