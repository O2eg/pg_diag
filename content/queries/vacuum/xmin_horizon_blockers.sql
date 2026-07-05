with activity as (
  select
    'pg_stat_activity'::text as component,
    'data'::text as horizon_type,
    coalesce(datname, '')::text as blocker_database,
    coalesce(usename, '')::text as blocker_user,
    coalesce(application_name, '')::text as blocker_appname,
    coalesce(state, '')::text as blocker_state,
    coalesce(to_jsonb(a)->>'query_id', '')::text as query_id,
    ''::text as slot_name,
    ''::text as slot_type,
    ''::text as slot_plugin,
    ''::text as slot_xmin_source,
    ''::text as slot_status,
    ''::text as slot_wal_status,
    ''::text as slot_inactive_since,
    ''::text as slot_conflicting,
    ''::text as slot_invalidation_reason,
    ''::text as replication_state,
    ''::text as replication_sync_state,
    ''::text as standby_name,
    ''::text as prepared_gid,
    ''::text as owner,
    age(backend_xmin)::int8 as age_tx
  from pg_stat_activity as a
  where
    pid <> pg_backend_pid()
    and backend_type = 'client backend'
    and backend_xmin is not null
  order by age(backend_xmin) desc, pid asc
  limit 1
),
slots as (
  select
    'pg_replication_slots'::text as component,
    'data'::text as horizon_type,
    coalesce(database, '')::text as blocker_database,
    ''::text as blocker_user,
    ''::text as blocker_appname,
    case when active then 'active' else 'inactive' end::text as blocker_state,
    ''::text as query_id,
    slot_name::text as slot_name,
    slot_type::text as slot_type,
    coalesce(plugin, '')::text as slot_plugin,
    'xmin'::text as slot_xmin_source,
    case
      when coalesce(to_jsonb(s)->>'invalidation_reason', '') <> '' then 'invalidated'
      when coalesce(to_jsonb(s)->>'conflicting', 'false') = 'true' then 'conflicting'
      when not active and coalesce(to_jsonb(s)->>'inactive_since', '') <> '' then 'inactive'
      when not active then 'unused'
      else 'active'
    end::text as slot_status,
    coalesce(to_jsonb(s)->>'wal_status', '')::text as slot_wal_status,
    coalesce(to_jsonb(s)->>'inactive_since', '')::text as slot_inactive_since,
    coalesce(to_jsonb(s)->>'conflicting', '')::text as slot_conflicting,
    coalesce(to_jsonb(s)->>'invalidation_reason', '')::text as slot_invalidation_reason,
    ''::text as replication_state,
    ''::text as replication_sync_state,
    ''::text as standby_name,
    ''::text as prepared_gid,
    ''::text as owner,
    age(xmin)::int8 as age_tx
  from pg_replication_slots as s
  where xmin is not null
  order by age(xmin) desc, slot_name asc
  limit 1
),
slots_catalog as (
  select
    'pg_replication_slots_catalog'::text as component,
    'catalog'::text as horizon_type,
    coalesce(database, '')::text as blocker_database,
    ''::text as blocker_user,
    ''::text as blocker_appname,
    case when active then 'active' else 'inactive' end::text as blocker_state,
    ''::text as query_id,
    slot_name::text as slot_name,
    slot_type::text as slot_type,
    coalesce(plugin, '')::text as slot_plugin,
    'catalog_xmin'::text as slot_xmin_source,
    case
      when coalesce(to_jsonb(s)->>'invalidation_reason', '') <> '' then 'invalidated'
      when coalesce(to_jsonb(s)->>'conflicting', 'false') = 'true' then 'conflicting'
      when not active and coalesce(to_jsonb(s)->>'inactive_since', '') <> '' then 'inactive'
      when not active then 'unused'
      else 'active'
    end::text as slot_status,
    coalesce(to_jsonb(s)->>'wal_status', '')::text as slot_wal_status,
    coalesce(to_jsonb(s)->>'inactive_since', '')::text as slot_inactive_since,
    coalesce(to_jsonb(s)->>'conflicting', '')::text as slot_conflicting,
    coalesce(to_jsonb(s)->>'invalidation_reason', '')::text as slot_invalidation_reason,
    ''::text as replication_state,
    ''::text as replication_sync_state,
    ''::text as standby_name,
    ''::text as prepared_gid,
    ''::text as owner,
    age(catalog_xmin)::int8 as age_tx
  from pg_replication_slots as s
  where catalog_xmin is not null
  order by age(catalog_xmin) desc, slot_name asc
  limit 1
),
replication as (
  select
    'pg_stat_replication'::text as component,
    'data'::text as horizon_type,
    ''::text as blocker_database,
    coalesce(usename, '')::text as blocker_user,
    coalesce(application_name, '')::text as blocker_appname,
    ''::text as blocker_state,
    ''::text as query_id,
    ''::text as slot_name,
    ''::text as slot_type,
    ''::text as slot_plugin,
    ''::text as slot_xmin_source,
    ''::text as slot_status,
    ''::text as slot_wal_status,
    ''::text as slot_inactive_since,
    ''::text as slot_conflicting,
    ''::text as slot_invalidation_reason,
    coalesce(state, '')::text as replication_state,
    coalesce(sync_state, '')::text as replication_sync_state,
    coalesce(application_name, '')::text as standby_name,
    ''::text as prepared_gid,
    ''::text as owner,
    age(backend_xmin)::int8 as age_tx
  from pg_stat_replication
  where backend_xmin is not null
  order by age(backend_xmin) desc, pid asc
  limit 1
),
prepared as (
  select
    'pg_prepared_xacts'::text as component,
    'data'::text as horizon_type,
    coalesce(database, '')::text as blocker_database,
    ''::text as blocker_user,
    ''::text as blocker_appname,
    ''::text as blocker_state,
    ''::text as query_id,
    ''::text as slot_name,
    ''::text as slot_type,
    ''::text as slot_plugin,
    ''::text as slot_xmin_source,
    ''::text as slot_status,
    ''::text as slot_wal_status,
    ''::text as slot_inactive_since,
    ''::text as slot_conflicting,
    ''::text as slot_invalidation_reason,
    ''::text as replication_state,
    ''::text as replication_sync_state,
    ''::text as standby_name,
    gid::text as prepared_gid,
    owner::text as owner,
    age(transaction)::int8 as age_tx
  from pg_prepared_xacts
  order by age(transaction) desc, gid asc
  limit 1
)
select
  current_database() as datname,
  component,
  horizon_type,
  blocker_database,
  blocker_user,
  blocker_appname,
  blocker_state,
  query_id,
  slot_name,
  slot_type,
  slot_plugin,
  slot_xmin_source,
  slot_status,
  slot_wal_status,
  slot_inactive_since,
  slot_conflicting,
  slot_invalidation_reason,
  replication_state,
  replication_sync_state,
  standby_name,
  prepared_gid,
  owner,
  age_tx
from activity
union all
select current_database(), component, horizon_type, blocker_database, blocker_user, blocker_appname, blocker_state, query_id, slot_name, slot_type, slot_plugin, slot_xmin_source, slot_status, slot_wal_status, slot_inactive_since, slot_conflicting, slot_invalidation_reason, replication_state, replication_sync_state, standby_name, prepared_gid, owner, age_tx
from slots
union all
select current_database(), component, horizon_type, blocker_database, blocker_user, blocker_appname, blocker_state, query_id, slot_name, slot_type, slot_plugin, slot_xmin_source, slot_status, slot_wal_status, slot_inactive_since, slot_conflicting, slot_invalidation_reason, replication_state, replication_sync_state, standby_name, prepared_gid, owner, age_tx
from slots_catalog
union all
select current_database(), component, horizon_type, blocker_database, blocker_user, blocker_appname, blocker_state, query_id, slot_name, slot_type, slot_plugin, slot_xmin_source, slot_status, slot_wal_status, slot_inactive_since, slot_conflicting, slot_invalidation_reason, replication_state, replication_sync_state, standby_name, prepared_gid, owner, age_tx
from replication
union all
select current_database(), component, horizon_type, blocker_database, blocker_user, blocker_appname, blocker_state, query_id, slot_name, slot_type, slot_plugin, slot_xmin_source, slot_status, slot_wal_status, slot_inactive_since, slot_conflicting, slot_invalidation_reason, replication_state, replication_sync_state, standby_name, prepared_gid, owner, age_tx
from prepared
