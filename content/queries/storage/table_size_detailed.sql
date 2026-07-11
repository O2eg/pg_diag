with candidates as materialized (
  select
    c.oid as table_oid,
    c.reltoastrelid,
    n.nspname as schema,
    c.relname as table_name,
    greatest(c.relpages, 0)::int8 * current_setting('block_size')::int8
      as estimated_heap_bytes
  from pg_catalog.pg_class c
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where c.relkind in ('r', 'p', 'm')
    and n.nspname not in ('pg_catalog', 'information_schema', 'pg_toast')
    and n.nspname !~ '^pg_temp_'
    and not exists (
      select 1
      from pg_catalog.pg_locks l
      where l.relation = c.oid
        and l.mode = 'AccessExclusiveLock'
        and l.granted
    )
  order by estimated_heap_bytes desc, n.nspname, c.relname
  limit 200
),
sizes as (
  select
    current_database() as datname,
    c.table_oid,
    c.schema,
    c.table_name,
    c.estimated_heap_bytes,
    pg_catalog.pg_relation_size(c.table_oid, 'main') as table_main_size_b,
    pg_catalog.pg_relation_size(c.table_oid, 'fsm') as table_fsm_size_b,
    pg_catalog.pg_relation_size(c.table_oid, 'vm') as table_vm_size_b,
    pg_catalog.pg_indexes_size(c.table_oid) as table_indexes_size_b,
    case when c.reltoastrelid <> 0 then pg_catalog.pg_relation_size(c.reltoastrelid, 'main') else 0 end
      as toast_main_size_b,
    case when c.reltoastrelid <> 0 then pg_catalog.pg_relation_size(c.reltoastrelid, 'fsm') else 0 end
      as toast_fsm_size_b,
    case when c.reltoastrelid <> 0 then pg_catalog.pg_relation_size(c.reltoastrelid, 'vm') else 0 end
      as toast_vm_size_b,
    case when c.reltoastrelid <> 0 then pg_catalog.pg_indexes_size(c.reltoastrelid) else 0 end
      as toast_indexes_size_b,
    pg_catalog.pg_total_relation_size(c.table_oid) as total_relation_size_b
  from candidates c
)
select
  datname,
  table_oid,
  schema,
  table_name,
  estimated_heap_bytes,
  table_main_size_b,
  table_fsm_size_b,
  table_vm_size_b,
  table_indexes_size_b,
  toast_main_size_b,
  toast_fsm_size_b,
  toast_vm_size_b,
  toast_indexes_size_b,
  total_relation_size_b,
  (toast_main_size_b + toast_fsm_size_b + toast_vm_size_b + toast_indexes_size_b)::int8
    as total_toast_size_b
from sizes
order by total_relation_size_b desc nulls last, schema, table_name
limit 100
