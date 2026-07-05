with table_sizes as (
  select
    current_database() as datname,
    n.nspname as schema,
    c.relname as table_name,
    c.oid as table_oid,
    c.reltoastrelid,
    pg_relation_size(c.oid, 'main') as table_main_size_b,
    pg_relation_size(c.oid, 'fsm') as table_fsm_size_b,
    pg_relation_size(c.oid, 'vm') as table_vm_size_b,
    pg_indexes_size(c.oid) as table_indexes_size_b,
    pg_relation_size(c.reltoastrelid, 'main') as toast_main_size_b,
    pg_relation_size(c.reltoastrelid, 'fsm') as toast_fsm_size_b,
    pg_relation_size(c.reltoastrelid, 'vm') as toast_vm_size_b,
    pg_indexes_size(c.reltoastrelid) as toast_indexes_size_b,
    pg_total_relation_size(c.reltoastrelid) as toast_total_size_b,
    pg_total_relation_size(c.oid) as total_relation_size_b
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  where c.relkind in ('r', 'p', 'm')
    and n.nspname not in ('information_schema', 'pg_toast')
    and not exists (
      select 1 from pg_locks
      where relation = c.oid and mode = 'AccessExclusiveLock'
    )
),
ranked as (
  select
    row_number() over (
      order by total_relation_size_b desc nulls last,
               schema, table_name
    ) as rownum,
    *
  from table_sizes
  where total_relation_size_b > 0
)
select
  datname,
  schema,
  table_name,
  abs(greatest(ceil(log((total_relation_size_b + 1) / 10 ^ 6)), 0))::text as size_cardinality_mb,
  table_main_size_b,
  table_fsm_size_b,
  table_vm_size_b,
  table_indexes_size_b,
  toast_main_size_b,
  toast_fsm_size_b,
  toast_vm_size_b,
  toast_indexes_size_b,
  total_relation_size_b,
  (toast_main_size_b + toast_fsm_size_b + toast_vm_size_b + toast_indexes_size_b) as total_toast_size_b
from ranked
where rownum <= 100
union all
select
  current_database() as datname,
  '$other$'::text as schema,
  '$other$'::text as table_name,
  abs(greatest(ceil(log((coalesce(sum(total_relation_size_b), 0) + 1) / 10 ^ 6)), 0))::text as size_cardinality_mb,
  coalesce(sum(table_main_size_b), 0)::int8 as table_main_size_b,
  coalesce(sum(table_fsm_size_b), 0)::int8 as table_fsm_size_b,
  coalesce(sum(table_vm_size_b), 0)::int8 as table_vm_size_b,
  coalesce(sum(table_indexes_size_b), 0)::int8 as table_indexes_size_b,
  coalesce(sum(toast_main_size_b), 0)::int8 as toast_main_size_b,
  coalesce(sum(toast_fsm_size_b), 0)::int8 as toast_fsm_size_b,
  coalesce(sum(toast_vm_size_b), 0)::int8 as toast_vm_size_b,
  coalesce(sum(toast_indexes_size_b), 0)::int8 as toast_indexes_size_b,
  coalesce(sum(total_relation_size_b), 0)::int8 as total_relation_size_b,
  coalesce(sum(toast_main_size_b + toast_fsm_size_b + toast_vm_size_b + toast_indexes_size_b), 0)::int8 as total_toast_size_b
from ranked
where rownum > 100
group by ()
having count(*) > 0
