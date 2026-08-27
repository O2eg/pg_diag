with rels_bounded as (
  select r.srsubid, r.srrelid, r.srsubstate, r.srsublsn
  from pg_catalog.pg_subscription_rel r
  order by case when r.srsubstate = 'r' then 1 else 0 end, r.srsubid, r.srrelid
  limit 3001
),
rels as (
  select * from rels_bounded limit 3000
),
subscriptions as (
  select distinct w.subid, w.subname
  from pg_catalog.pg_stat_subscription w
),
apply_workers as (
  select w.subid, bool_or(w.pid is not null) as apply_worker_running
  from pg_catalog.pg_stat_subscription w
  where w.relid is null
  group by w.subid
),
sync_workers as (
  select w.subid, w.relid, min(w.pid) as pid
  from pg_catalog.pg_stat_subscription w
  where w.relid is not null
  group by w.subid, w.relid
),
per_subscription as (
  select
    srsubid,
    count(*)::int8 as sampled_tables,
    count(*) filter (where srsubstate = 'r')::int8 as sampled_ready_tables,
    count(*) filter (where srsubstate <> 'r')::int8 as sampled_not_ready_tables
  from rels
  group by srsubid
),
coverage as (
  select (select count(*) > 3000 from rels_bounded) as result_truncated
),
findings as (
  select
    coalesce(s.subname::text, '[subscription ' || r.srsubid::text || ']') as subscription_name,
    coalesce(aw.apply_worker_running, false) as apply_worker_running,
    n.nspname::text as schema_name,
    c.relname::text as table_name,
    r.srsubstate::text as state_code,
    case r.srsubstate
      when 'i' then 'initialize'
      when 'd' then 'data copy'
      when 'f' then 'finished copy'
      when 's' then 'synchronized'
      when 'r' then 'ready'
      else r.srsubstate::text
    end as state,
    r.srsublsn::text as synchronized_lsn,
    sw.pid as sync_worker_pid,
    (sw.pid is not null) as sync_worker_running,
    ps.sampled_tables,
    ps.sampled_ready_tables,
    ps.sampled_not_ready_tables,
    cov.result_truncated,
    case
      when r.srsubstate = 'r' then 'ok'
      when sw.pid is not null then 'unknown'
      when coalesce(aw.apply_worker_running, false) then 'medium'
      else 'unknown'
    end as risk_level,
    case
      when r.srsubstate = 'r' then ''
      when sw.pid is not null
        then 'Initial table synchronization is in progress'
      when coalesce(aw.apply_worker_running, false)
        then 'Table is not ready and no synchronization worker is running; check max_sync_workers_per_subscription, worker errors, and the publisher'
      else 'Table is not ready and the subscription apply worker is not running'
    end as risk_reason
  from rels r
  left join subscriptions s on s.subid = r.srsubid
  left join apply_workers aw on aw.subid = r.srsubid
  left join sync_workers sw on sw.subid = r.srsubid and sw.relid = r.srrelid
  left join per_subscription ps on ps.srsubid = r.srsubid
  left join pg_catalog.pg_class c on c.oid = r.srrelid
  left join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  cross join coverage cov
),
combined as (
  select * from findings
  union all
  select
    '[coverage]'::text, false, ''::text, ''::text, ''::text, ''::text, null::text, null::int, false,
    null::int8, null::int8, null::int8, true, 'unknown'::text,
    'More than 3000 subscription tables exist; findings above are proven but the list is incomplete'::text
  from coverage
  where coverage.result_truncated
)
select *
from combined
order by
  case risk_level when 'medium' then 0 when 'unknown' then 1 else 2 end,
  subscription_name,
  schema_name,
  table_name
