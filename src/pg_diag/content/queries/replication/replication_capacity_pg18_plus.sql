with current_lsn as (
  select
    case
      when pg_catalog.pg_is_in_recovery()
        then coalesce(pg_catalog.pg_last_wal_receive_lsn(), pg_catalog.pg_last_wal_replay_lsn())
      else pg_catalog.pg_current_wal_lsn()
    end as lsn
),
walsenders as (
  select
    count(*)::int8 as sender_backends
  from pg_catalog.pg_stat_activity a
  where a.backend_type = 'walsender'
),
sender_states as (
  select
    count(*) filter (where state = 'streaming')::int8 as streaming_senders,
    count(*) filter (where state = 'backup')::int8 as backup_senders,
    count(*) filter (where state not in ('streaming', 'backup'))::int8 as other_senders
  from pg_catalog.pg_stat_replication
),
slots_bounded as (
  select
    s.slot_name,
    s.active,
    s.slot_type,
    case
      when s.restart_lsn is null then null
      else pg_catalog.pg_wal_lsn_diff(c.lsn, s.restart_lsn)::int8
    end as retained_wal_bytes
  from pg_catalog.pg_replication_slots s
  cross join current_lsn c
  order by s.slot_name
  limit 10001
),
slots as (
  select
    count(*)::int8 as slot_count,
    count(*) filter (where active)::int8 as active_slots,
    count(*) filter (where not active)::int8 as inactive_slots,
    count(*) filter (where slot_type = 'logical')::int8 as logical_slots,
    max(retained_wal_bytes)::int8 as max_retained_wal_bytes
  from (select * from slots_bounded limit 10000) b
),
origins as (
  select
    (
      select count(*)::int8
      from (select roident from pg_catalog.pg_replication_origin limit 10000) created
    ) as created_origin_count,
    (
      select count(*)::int8
      from pg_catalog.pg_stat_subscription w
      where w.pid is not null
    ) as origin_using_worker_count
),
subscription_workers as (
  select
    count(*) filter (where w.pid is not null)::int8 as running_workers,
    coalesce(max(per_sub.sync_workers), 0)::int8 as max_sync_workers_one_subscription,
    coalesce(max(per_sub.parallel_workers), 0)::int8 as max_parallel_workers_one_subscription
  from pg_catalog.pg_stat_subscription w
  left join (
    select
      subid,
      count(*) filter (where relid is not null)::int8 as sync_workers,
      count(*) filter (where worker_type = 'parallel apply')::int8 as parallel_workers
    from pg_catalog.pg_stat_subscription
    group by subid
  ) per_sub on per_sub.subid = w.subid
),
publications as (
  select count(*)::int8 as publication_count
  from (select oid from pg_catalog.pg_publication limit 10000) p
),
resources as (
  select
    1 as ord,
    'wal_senders'::text as resource,
    'max_wal_senders'::text as setting_name,
    current_setting('max_wal_senders') as setting_value,
    current_setting('max_wal_senders')::int8 as limit_value,
    ws.sender_backends as used_value,
    'streaming ' || ss.streaming_senders::text || ', backup ' || ss.backup_senders::text
      || ', other ' || ss.other_senders::text as detail
  from walsenders ws cross join sender_states ss
  union all
  select
    2,
    'replication_slots',
    'max_replication_slots',
    current_setting('max_replication_slots'),
    current_setting('max_replication_slots')::int8,
    sl.slot_count,
    'active ' || sl.active_slots::text || ', inactive ' || sl.inactive_slots::text
      || ', logical ' || sl.logical_slots::text
  from slots sl
  union all
  select
    3,
    'replication_origins',
    'max_active_replication_origins',
    current_setting('max_active_replication_origins'),
    current_setting('max_active_replication_origins')::int8,
    o.origin_using_worker_count,
    'running subscription apply and synchronization workers, each holding one tracked origin (lower bound; '
      || o.created_origin_count::text
      || ' origin(s) are created and pg_replication_origin_status needs superuser)'
  from origins o
  union all
  select
    4,
    'logical_replication_workers',
    'max_logical_replication_workers',
    current_setting('max_logical_replication_workers'),
    current_setting('max_logical_replication_workers')::int8,
    sw.running_workers,
    'apply, table synchronization, and parallel apply workers of all subscriptions'
  from subscription_workers sw
  union all
  select
    5,
    'sync_workers_per_subscription',
    'max_sync_workers_per_subscription',
    current_setting('max_sync_workers_per_subscription'),
    current_setting('max_sync_workers_per_subscription')::int8,
    sw.max_sync_workers_one_subscription,
    'largest number of table synchronization workers used by one subscription'
  from subscription_workers sw
  union all
  select
    6,
    'parallel_apply_workers_per_subscription',
    'max_parallel_apply_workers_per_subscription',
    current_setting('max_parallel_apply_workers_per_subscription'),
    current_setting('max_parallel_apply_workers_per_subscription')::int8,
    sw.max_parallel_workers_one_subscription,
    'largest number of parallel apply workers used by one subscription'
  from subscription_workers sw
  union all
  select
    7,
    'wal_level',
    'wal_level',
    current_setting('wal_level'),
    null::int8,
    null::int8,
    case
      when current_setting('wal_level') = 'logical' then 'logical decoding is available'
      when p.publication_count > 0
        then p.publication_count::text || ' publication(s) exist in the connected database but wal_level is not logical'
      else 'physical replication only'
    end
  from publications p
  union all
  select
    8,
    'wal_keep',
    'wal_keep_size',
    current_setting('wal_keep_size'),
    pg_catalog.pg_size_bytes(current_setting('wal_keep_size'))::int8,
    null::int8,
    'WAL kept for standbys that stream without a slot; independent of slot retention'
  from slots sl
  union all
  select
    9,
    'slot_wal_keep',
    'max_slot_wal_keep_size',
    current_setting('max_slot_wal_keep_size'),
    case
      when current_setting('max_slot_wal_keep_size') = '-1' then null
      else pg_catalog.pg_size_bytes(current_setting('max_slot_wal_keep_size'))
    end::int8,
    sl.max_retained_wal_bytes,
    'largest WAL retained by any slot against the slot invalidation limit'
  from slots sl
),
findings as (
  select
    r.ord,
    r.resource,
    r.setting_name,
    r.setting_value,
    r.limit_value,
    r.used_value,
    case
      when r.limit_value is null or r.used_value is null then null
      else greatest(r.limit_value - r.used_value, 0)
    end::int8 as available_value,
    case
      when r.limit_value is null or r.limit_value <= 0 or r.used_value is null then null
      else (r.used_value * 100.0 / r.limit_value)::float8
    end as utilization_pct,
    r.detail
  from resources r
)
select
  f.resource,
  f.setting_name,
  f.setting_value,
  f.limit_value,
  f.used_value,
  f.available_value,
  f.utilization_pct,
  f.detail,
  case
    when f.resource = 'wal_level' and current_setting('wal_level') <> 'logical'
      and (select publication_count from publications) > 0 then 'medium'
    when f.resource = 'wal_level' then 'ok'
    when f.resource = 'slot_wal_keep' and f.utilization_pct >= 80 then 'medium'
    when f.resource in ('wal_keep', 'slot_wal_keep') then 'ok'
    when f.utilization_pct >= 100 then 'high'
    when f.utilization_pct >= 90 then 'medium'
    else 'ok'
  end as risk_level,
  case
    when f.resource = 'wal_level' and current_setting('wal_level') <> 'logical'
      and (select publication_count from publications) > 0
      then 'Publications exist but wal_level is not logical; subscribers cannot decode changes'
    when f.resource = 'slot_wal_keep' and f.utilization_pct >= 80
      then 'A replication slot retains at least 80 percent of max_slot_wal_keep_size and will be invalidated when the limit is exceeded'
    when f.resource in ('wal_level', 'wal_keep', 'slot_wal_keep') then ''
    when f.utilization_pct >= 100
      then 'All ' || f.resource || ' are in use; new standbys, backups, or workers cannot start'
    when f.utilization_pct >= 90
      then 'At least 90 percent of ' || f.resource || ' are in use'
    else ''
  end as risk_reason
from findings f
order by f.ord
