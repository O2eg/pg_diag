with snapshot as (
  select txid_snapshot_xmin(txid_current_snapshot())::int8 as snapshot_xmin
),
activity as (
  select
    max(age(backend_xmin))::int8 as pg_stat_activity_age_tx,
    count(*)::int8 as pg_stat_activity_count
  from pg_stat_activity
  where
    pid <> pg_backend_pid()
    and backend_type = 'client backend'
    and backend_xmin is not null
),
slots as (
  select
    max(age(xmin))::int8 as pg_replication_slots_age_tx,
    count(*)::int8 as pg_replication_slots_count
  from pg_replication_slots
  where xmin is not null
),
slots_catalog as (
  select
    max(age(catalog_xmin))::int8 as pg_replication_slots_catalog_age_tx,
    count(*)::int8 as pg_replication_slots_catalog_count
  from pg_replication_slots
  where catalog_xmin is not null
),
replication as (
  select
    max(age(backend_xmin))::int8 as pg_stat_replication_age_tx,
    count(*)::int8 as pg_stat_replication_count
  from pg_stat_replication
  where backend_xmin is not null
),
prepared as (
  select
    max(age(transaction))::int8 as pg_prepared_xacts_age_tx,
    count(*)::int8 as pg_prepared_xacts_count
  from pg_prepared_xacts
),
summary as (
  select
    (select snapshot_xmin from snapshot) as snapshot_xmin,
    coalesce((select pg_stat_activity_age_tx from activity), 0) as pg_stat_activity_age_tx,
    coalesce((select pg_stat_activity_count from activity), 0) as pg_stat_activity_count,
    coalesce((select pg_replication_slots_age_tx from slots), 0) as pg_replication_slots_age_tx,
    coalesce((select pg_replication_slots_count from slots), 0) as pg_replication_slots_count,
    coalesce((select pg_replication_slots_catalog_age_tx from slots_catalog), 0) as pg_replication_slots_catalog_age_tx,
    coalesce((select pg_replication_slots_catalog_count from slots_catalog), 0) as pg_replication_slots_catalog_count,
    coalesce((select pg_stat_replication_age_tx from replication), 0) as pg_stat_replication_age_tx,
    coalesce((select pg_stat_replication_count from replication), 0) as pg_stat_replication_count,
    coalesce((select pg_prepared_xacts_age_tx from prepared), 0) as pg_prepared_xacts_age_tx,
    coalesce((select pg_prepared_xacts_count from prepared), 0) as pg_prepared_xacts_count
)
select
  current_database() as datname,
  snapshot_xmin,
  pg_stat_activity_age_tx,
  pg_stat_activity_count,
  pg_replication_slots_age_tx,
  pg_replication_slots_count,
  pg_replication_slots_catalog_age_tx,
  pg_replication_slots_catalog_count,
  pg_stat_replication_age_tx,
  pg_stat_replication_count,
  pg_prepared_xacts_age_tx,
  pg_prepared_xacts_count,
  greatest(
    pg_stat_activity_age_tx,
    pg_replication_slots_age_tx,
    pg_stat_replication_age_tx,
    pg_prepared_xacts_age_tx
  ) as data_horizon_age_tx,
  greatest(
    pg_stat_activity_age_tx,
    pg_replication_slots_age_tx,
    pg_stat_replication_age_tx,
    pg_prepared_xacts_age_tx,
    pg_replication_slots_catalog_age_tx
  ) as catalog_horizon_age_tx
from summary
