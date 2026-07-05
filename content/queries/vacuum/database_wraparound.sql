with settings as (
  select
    current_setting('autovacuum_freeze_max_age')::numeric as freeze_max_age,
    current_setting('autovacuum_multixact_freeze_max_age')::numeric as multixact_freeze_max_age
)
select
  d.datname,
  age(d.datfrozenxid)::int8 as xid_age,
  round(age(d.datfrozenxid)::numeric * 100 / nullif(s.freeze_max_age, 0), 3) as xid_age_pct,
  mxid_age(d.datminmxid)::int8 as multixact_age,
  round(mxid_age(d.datminmxid)::numeric * 100 / nullif(s.multixact_freeze_max_age, 0), 3) as multixact_age_pct,
  d.datfrozenxid::text as datfrozenxid,
  d.datminmxid::text as datminmxid,
  s.freeze_max_age::int8 as autovacuum_freeze_max_age,
  s.multixact_freeze_max_age::int8 as autovacuum_multixact_freeze_max_age
from pg_database d
cross join settings s
where d.datallowconn
order by xid_age desc
