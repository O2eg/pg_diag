with settings as (
  select
    current_setting('autovacuum_freeze_max_age')::numeric as freeze_max_age,
    current_setting('autovacuum_multixact_freeze_max_age')::numeric as multixact_freeze_max_age,
    current_setting('vacuum_failsafe_age')::numeric as failsafe_age,
    current_setting('vacuum_multixact_failsafe_age')::numeric as multixact_failsafe_age
)
select
  d.oid as datid,
  d.datname,
  age(d.datfrozenxid)::int8 as xid_age,
  (age(d.datfrozenxid)::numeric * 100 / nullif(s.freeze_max_age, 0))
    as xid_freeze_trigger_pct,
  (age(d.datfrozenxid)::numeric * 100 / nullif(s.failsafe_age, 0))
    as xid_failsafe_pct,
  mxid_age(d.datminmxid)::int8 as multixact_age,
  (mxid_age(d.datminmxid)::numeric * 100 / nullif(s.multixact_freeze_max_age, 0))
    as multixact_freeze_trigger_pct,
  (mxid_age(d.datminmxid)::numeric * 100 / nullif(s.multixact_failsafe_age, 0))
    as multixact_failsafe_pct,
  d.datfrozenxid::text as datfrozenxid,
  d.datminmxid::text as datminmxid,
  s.freeze_max_age::int8 as autovacuum_freeze_max_age,
  s.multixact_freeze_max_age::int8 as autovacuum_multixact_freeze_max_age,
  s.failsafe_age::int8 as vacuum_failsafe_age,
  s.multixact_failsafe_age::int8 as vacuum_multixact_failsafe_age,
  case
    when age(d.datfrozenxid)::numeric >= s.failsafe_age
      or mxid_age(d.datminmxid)::numeric >= s.multixact_failsafe_age then 'high'
    when age(d.datfrozenxid)::numeric >= s.freeze_max_age
      or mxid_age(d.datminmxid)::numeric >= s.multixact_freeze_max_age then 'medium'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when age(d.datfrozenxid)::numeric >= s.failsafe_age
      or mxid_age(d.datminmxid)::numeric >= s.multixact_failsafe_age
      then 'database age crossed a vacuum failsafe threshold'
    when age(d.datfrozenxid)::numeric >= s.freeze_max_age
      or mxid_age(d.datminmxid)::numeric >= s.multixact_freeze_max_age
      then 'database age crossed an autovacuum freeze threshold'
    else ''
  end as pg_diag_internal_reason
from pg_database d
cross join settings s
where d.datallowconn
order by greatest(age(d.datfrozenxid), mxid_age(d.datminmxid)) desc
