with tracked_bounded as (
  select c.oid, c.collname, c.collnamespace, c.collprovider, c.collversion
  from pg_catalog.pg_collation c
  where c.collversion is not null
  order by c.oid
  limit 1001
),
tracked_sample as (
  select * from tracked_bounded limit 1000
),
versions as (
  select t.*, pg_catalog.pg_collation_actual_version(t.oid) as actual_version
  from tracked_sample t
),
mismatched as (
  select * from versions where actual_version is distinct from collversion
),
coverage as (
  select (select count(*) > 1000 from tracked_bounded) as collation_sample_truncated
),
db_default as (
  select
    case d.datlocprovider when 'i' then 'icu' when 'c' then 'libc' when 'b' then 'builtin' else d.datlocprovider::text end as provider,
    d.datcollversion as recorded_version,
    pg_catalog.pg_database_collation_actual_version(d.oid) as actual_version
  from pg_catalog.pg_database d
  where d.datname = current_database()
    and d.datcollversion is not null
)
select
  n.nspname as schema_name,
  m.collname as collation_name,
  case m.collprovider when 'i' then 'icu' when 'c' then 'libc' else m.collprovider::text end as provider,
  m.collversion as recorded_version,
  m.actual_version,
  (
    select count(*)::int8
    from pg_catalog.pg_depend d
    where d.refclassid = 'pg_catalog.pg_collation'::regclass
      and d.refobjid = m.oid
      and d.classid = 'pg_catalog.pg_class'::regclass
  ) as dependent_relation_count,
  coverage.collation_sample_truncated,
  'high' as risk_level,
  'Collation was recorded with version ' || m.collversion || ' but the operating system now provides '
    || coalesce(m.actual_version, 'none')
    || '; sort order may have changed and dependent indexes need REINDEX' as risk_reason
from mismatched m
join pg_catalog.pg_namespace n on n.oid = m.collnamespace
cross join coverage

union all

select
  null::text as schema_name,
  '(database default)'::text as collation_name,
  db.provider,
  db.recorded_version,
  db.actual_version,
  null::int8 as dependent_relation_count,
  coverage.collation_sample_truncated,
  'high' as risk_level,
  'The default collation of this database was recorded with version ' || db.recorded_version
    || ' but the operating system now provides ' || coalesce(db.actual_version, 'none')
    || '; sort order may have changed and indexes on affected text columns need REINDEX' as risk_reason
from db_default db
cross join coverage
where db.actual_version is distinct from db.recorded_version

union all

select
  null::text as schema_name,
  '[coverage]'::text as collation_name,
  null::text as provider,
  null::text as recorded_version,
  null::text as actual_version,
  null::int8 as dependent_relation_count,
  true as collation_sample_truncated,
  'unknown'::text as risk_level,
  'More than 1000 version-tracked collations exist; the mismatch check covered only the first 1000' as risk_reason
from coverage
where coverage.collation_sample_truncated

order by schema_name nulls first, collation_name
