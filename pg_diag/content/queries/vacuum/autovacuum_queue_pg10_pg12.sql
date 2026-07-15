with settings as (
  select
    current_setting('autovacuum_vacuum_threshold')::float8 as vacuum_threshold,
    current_setting('autovacuum_vacuum_scale_factor')::float8 as vacuum_scale_factor,
    current_setting('autovacuum_freeze_max_age')::int8 as freeze_max_age,
    current_setting('autovacuum_multixact_freeze_max_age')::int8 as mx_freeze_max_age
),
table_options as (
  select
    c.oid as relid,
    n.nspname as schemaname,
    c.relname,
    greatest(c.reltuples, 0)::float8 as reltuples,
    age(c.relfrozenxid)::int8 as xid_age,
    mxid_age(c.relminmxid)::int8 as mxid_age,
    coalesce((o.options->>'autovacuum_enabled')::boolean, true) as autovacuum_enabled,
    coalesce((o.options->>'autovacuum_vacuum_threshold')::float8, s.vacuum_threshold)
      as vacuum_base,
    coalesce((o.options->>'autovacuum_vacuum_scale_factor')::float8, s.vacuum_scale_factor)
      as vacuum_scale,
    coalesce((o.options->>'autovacuum_freeze_max_age')::int8, s.freeze_max_age)
      as freeze_max_age,
    coalesce((o.options->>'autovacuum_multixact_freeze_max_age')::int8, s.mx_freeze_max_age)
      as mx_freeze_max_age
  from pg_catalog.pg_class c
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  cross join settings s
  cross join lateral (
    select coalesce(jsonb_object_agg(option_name, option_value), '{}'::jsonb) as options
    from pg_catalog.pg_options_to_table(c.reloptions)
  ) o
  where c.relkind in ('r', 'm')
    and c.relpersistence <> 't'
    and n.nspname not in ('pg_catalog', 'information_schema')
    and n.nspname !~ '^pg_toast'
),
eligibility as (
  select
    current_database() as datname,
    t.relid,
    t.schemaname,
    t.relname,
    t.reltuples::int8 as estimated_rows,
    st.n_live_tup::int8 as n_live_tup,
    st.n_dead_tup::int8 as n_dead_tup,
    null::int8 as n_ins_since_vacuum,
    t.autovacuum_enabled,
    (t.vacuum_base + t.vacuum_scale * t.reltuples)::int8 as vacuum_threshold,
    null::int8 as insert_threshold,
    t.xid_age,
    t.freeze_max_age,
    t.mxid_age,
    t.mx_freeze_max_age,
    st.last_vacuum,
    st.last_autovacuum,
    false as vacuum_in_progress
  from table_options t
  join pg_catalog.pg_stat_all_tables st on st.relid = t.relid
),
scored as (
  select
    e.*,
    e.n_dead_tup >= e.vacuum_threshold as dead_tuple_vacuum_due,
    false as insert_vacuum_due,
    e.xid_age >= e.freeze_max_age or e.mxid_age >= e.mx_freeze_max_age
      as wraparound_vacuum_due,
    (e.n_dead_tup::numeric / nullif(e.vacuum_threshold, 0))
      as dead_tuple_overdue_factor,
    null::numeric as insert_overdue_factor,
    (e.xid_age::numeric / nullif(e.freeze_max_age, 0)) as xid_overdue_factor,
    (e.mxid_age::numeric / nullif(e.mx_freeze_max_age, 0)) as mxid_overdue_factor
  from eligibility e
)
select
  datname,
  relid,
  schemaname,
  relname,
  estimated_rows,
  n_live_tup,
  n_dead_tup,
  n_ins_since_vacuum,
  autovacuum_enabled,
  vacuum_threshold,
  insert_threshold,
  xid_age,
  freeze_max_age,
  mxid_age,
  mx_freeze_max_age,
  dead_tuple_vacuum_due,
  insert_vacuum_due,
  wraparound_vacuum_due,
  vacuum_in_progress,
  dead_tuple_overdue_factor,
  insert_overdue_factor,
  xid_overdue_factor,
  mxid_overdue_factor,
  greatest(
    coalesce(xid_overdue_factor, 0),
    coalesce(mxid_overdue_factor, 0),
    coalesce(dead_tuple_overdue_factor, 0)
  ) as priority_factor,
  last_vacuum,
  last_autovacuum,
  case
    when wraparound_vacuum_due then 'high'
    when dead_tuple_vacuum_due then 'medium'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when wraparound_vacuum_due
      then 'table crossed an xid or multixact freeze threshold'
    when dead_tuple_vacuum_due
      then 'dead tuple estimate crossed the effective autovacuum threshold'
    else ''
  end as pg_diag_internal_reason
from scored
where n_dead_tup > 0
   or xid_overdue_factor >= 0.5
   or mxid_overdue_factor >= 0.5
order by
  wraparound_vacuum_due desc,
  priority_factor desc,
  n_dead_tup desc,
  schemaname,
  relname
limit 200
