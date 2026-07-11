with settings as (
  select
    current_setting('autovacuum_vacuum_threshold')::float8 as vacuum_threshold,
    current_setting('autovacuum_vacuum_scale_factor')::float8 as vacuum_scale_factor,
    current_setting('autovacuum_vacuum_insert_threshold')::float8 as insert_threshold,
    current_setting('autovacuum_vacuum_insert_scale_factor')::float8 as insert_scale_factor,
    current_setting('autovacuum_freeze_max_age')::int8 as freeze_max_age,
    current_setting('autovacuum_multixact_freeze_max_age')::int8 as mx_freeze_max_age,
    nullif(current_setting('autovacuum_vacuum_max_threshold', true), '')::float8
      as vacuum_max_threshold
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
    coalesce((o.options->>'autovacuum_vacuum_insert_threshold')::float8, s.insert_threshold)
      as insert_base,
    coalesce((o.options->>'autovacuum_vacuum_insert_scale_factor')::float8, s.insert_scale_factor)
      as insert_scale,
    coalesce((o.options->>'autovacuum_freeze_max_age')::int8, s.freeze_max_age)
      as freeze_max_age,
    coalesce((o.options->>'autovacuum_multixact_freeze_max_age')::int8, s.mx_freeze_max_age)
      as mx_freeze_max_age,
    s.vacuum_max_threshold
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
    st.n_ins_since_vacuum::int8 as n_ins_since_vacuum,
    t.autovacuum_enabled,
    least(
      t.vacuum_base + t.vacuum_scale * t.reltuples,
      coalesce(t.vacuum_max_threshold, t.vacuum_base + t.vacuum_scale * t.reltuples)
    )::int8 as vacuum_threshold,
    case
      when t.insert_base < 0 then null
      else (t.insert_base + t.insert_scale * t.reltuples)::int8
    end as insert_threshold,
    t.xid_age,
    t.freeze_max_age,
    t.mxid_age,
    t.mx_freeze_max_age,
    st.last_vacuum,
    st.last_autovacuum,
    exists (
      select 1 from pg_catalog.pg_stat_progress_vacuum p where p.relid = t.relid
    ) as vacuum_in_progress
  from table_options t
  join pg_catalog.pg_stat_all_tables st on st.relid = t.relid
),
scored as (
  select
    e.*,
    e.n_dead_tup >= e.vacuum_threshold as dead_tuple_vacuum_due,
    e.insert_threshold is not null and e.n_ins_since_vacuum >= e.insert_threshold
      as insert_vacuum_due,
    e.xid_age >= e.freeze_max_age or e.mxid_age >= e.mx_freeze_max_age
      as wraparound_vacuum_due,
    round(e.n_dead_tup::numeric / nullif(e.vacuum_threshold, 0), 3)
      as dead_tuple_overdue_factor,
    round(e.n_ins_since_vacuum::numeric / nullif(e.insert_threshold, 0), 3)
      as insert_overdue_factor,
    round(e.xid_age::numeric / nullif(e.freeze_max_age, 0), 3) as xid_overdue_factor,
    round(e.mxid_age::numeric / nullif(e.mx_freeze_max_age, 0), 3) as mxid_overdue_factor
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
    coalesce(dead_tuple_overdue_factor, 0),
    coalesce(insert_overdue_factor, 0)
  ) as priority_factor,
  last_vacuum,
  last_autovacuum,
  case
    when wraparound_vacuum_due and not vacuum_in_progress then 'high'
    when (dead_tuple_vacuum_due or insert_vacuum_due) and not vacuum_in_progress then 'medium'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when wraparound_vacuum_due and not vacuum_in_progress
      then 'table crossed an xid or multixact freeze threshold without active vacuum'
    when dead_tuple_vacuum_due and not vacuum_in_progress
      then 'dead tuple estimate crossed the effective autovacuum threshold'
    when insert_vacuum_due and not vacuum_in_progress
      then 'insert count crossed the insert-triggered vacuum threshold'
    else ''
  end as pg_diag_internal_reason
from scored
where n_dead_tup > 0
   or n_ins_since_vacuum > 0
   or xid_overdue_factor >= 0.5
   or mxid_overdue_factor >= 0.5
order by
  wraparound_vacuum_due desc,
  priority_factor desc,
  n_dead_tup desc,
  schemaname,
  relname
limit 200
