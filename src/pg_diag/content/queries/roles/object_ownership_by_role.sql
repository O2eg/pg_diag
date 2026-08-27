with storage_relation_roots_bounded as (
  select c.oid, c.relkind, c.relowner, greatest(coalesce(c.relpages, 0), 0)::int8 as relpages
  from pg_catalog.pg_class c
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where c.relkind in ('r', 'm')
    and greatest(coalesce(c.relpages, 0), 0) > 0
    and n.nspname not in ('pg_catalog', 'information_schema')
    and n.nspname not like 'pg_toast%'
  order by c.relpages desc, n.nspname, c.relname, c.oid
  limit 10001
),
storage_relation_candidates as (
  select * from storage_relation_roots_bounded limit 10000
),
named_relation_roots_bounded as (
  select c.oid, c.relkind, c.relowner, 0::int8 as relpages
  from pg_catalog.pg_class c
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where (
      c.relkind in ('p', 'S', 'v', 'f')
      or (c.relkind in ('r', 'm') and greatest(coalesce(c.relpages, 0), 0) = 0)
    )
    and n.nspname not in ('pg_catalog', 'information_schema')
    and n.nspname not like 'pg_toast%'
  order by n.nspname, c.relname, c.oid
  limit 10001
),
named_relation_candidates as (
  select * from named_relation_roots_bounded limit 10000
),
function_roots_bounded as (
  select p.oid, p.proowner
  from pg_catalog.pg_proc p
  join pg_catalog.pg_namespace n on n.oid = p.pronamespace
  left join pg_catalog.pg_stat_user_functions s on s.funcid = p.oid
  where n.nspname not in ('pg_catalog', 'information_schema')
    and n.nspname not like 'pg_toast%'
  order by coalesce(s.calls, 0) desc, n.nspname, p.proname, p.oid
  limit 1001
),
function_candidates as (
  select * from function_roots_bounded limit 1000
),
schema_roots_bounded as (
  select n.oid, n.nspowner
  from pg_catalog.pg_namespace n
  where n.nspname not in ('pg_catalog', 'information_schema')
    and n.nspname not like 'pg_toast%'
  order by n.nspname, n.oid
  limit 10001
),
schema_candidates as (
  select * from schema_roots_bounded limit 10000
),
owned as (
  select relowner as owner_oid, relkind::text as kind, relpages from storage_relation_candidates
  union all
  select relowner as owner_oid, relkind::text as kind, relpages from named_relation_candidates
  union all
  select proowner as owner_oid, 'function'::text as kind, 0::int8 as relpages from function_candidates
  union all
  select nspowner as owner_oid, 'schema'::text as kind, 0::int8 as relpages from schema_candidates
),
object_rollup as (
  select
    owner_oid,
    count(*) filter (where kind = 'schema')::int8 as sampled_schema_count,
    count(*) filter (where kind = 'r')::int8 as sampled_table_count,
    count(*) filter (where kind = 'p')::int8 as sampled_partitioned_table_count,
    count(*) filter (where kind = 'v')::int8 as sampled_view_count,
    count(*) filter (where kind = 'm')::int8 as sampled_materialized_view_count,
    count(*) filter (where kind = 'f')::int8 as sampled_foreign_table_count,
    count(*) filter (where kind = 'S')::int8 as sampled_sequence_count,
    count(*) filter (where kind = 'function')::int8 as sampled_function_count,
    sum(relpages)::int8 as sampled_relpages
  from owned
  group by owner_oid
),
database_rollup as (
  select d.datdba as owner_oid, count(*)::int8 as database_count
  from pg_catalog.pg_database d
  group by d.datdba
),
tablespace_rollup as (
  select t.spcowner as owner_oid, count(*)::int8 as tablespace_count
  from pg_catalog.pg_tablespace t
  group by t.spcowner
),
owners as (
  select owner_oid from object_rollup
  union
  select owner_oid from database_rollup
  union
  select owner_oid from tablespace_rollup
),
ranked_findings as (
  select
    coalesce(r.rolname::text, '[oid ' || o.owner_oid::text || ']') as role_name,
    o.owner_oid as role_oid,
    coalesce(r.rolcanlogin, false) as can_login,
    coalesce(r.rolsuper, false) as superuser,
    coalesce(db.database_count, 0)::int8 as database_count,
    coalesce(ts.tablespace_count, 0)::int8 as tablespace_count,
    coalesce(obj.sampled_schema_count, 0)::int8 as sampled_schema_count,
    coalesce(obj.sampled_table_count, 0)::int8 as sampled_table_count,
    coalesce(obj.sampled_partitioned_table_count, 0)::int8 as sampled_partitioned_table_count,
    coalesce(obj.sampled_view_count, 0)::int8 as sampled_view_count,
    coalesce(obj.sampled_materialized_view_count, 0)::int8 as sampled_materialized_view_count,
    coalesce(obj.sampled_foreign_table_count, 0)::int8 as sampled_foreign_table_count,
    coalesce(obj.sampled_sequence_count, 0)::int8 as sampled_sequence_count,
    coalesce(obj.sampled_function_count, 0)::int8 as sampled_function_count,
    coalesce(obj.sampled_relpages, 0)::int8 as sampled_relpages
  from owners o
  left join pg_catalog.pg_roles r on r.oid = o.owner_oid
  left join object_rollup obj on obj.owner_oid = o.owner_oid
  left join database_rollup db on db.owner_oid = o.owner_oid
  left join tablespace_rollup ts on ts.owner_oid = o.owner_oid
  order by coalesce(obj.sampled_relpages, 0) desc, role_name
  limit 1001
),
coverage as (
  select
    (
      (select count(*) > 10000 from storage_relation_roots_bounded)
      or (select count(*) > 10000 from named_relation_roots_bounded)
      or (select count(*) > 1000 from function_roots_bounded)
      or (select count(*) > 10000 from schema_roots_bounded)
    ) as candidate_sample_truncated,
    (select count(*) > 1000 from ranked_findings) as result_truncated
),
findings as (
  select * from ranked_findings limit 1000
)
select
  findings.*,
  coverage.candidate_sample_truncated,
  coverage.result_truncated,
  case
    when coverage.candidate_sample_truncated or coverage.result_truncated then 'unknown'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when coverage.candidate_sample_truncated
      then 'Object candidate pools were truncated; sampled ownership counts are partial'
    when coverage.result_truncated
      then 'More than 1000 owner roles exist; the ownership list is partial'
    else ''
  end as pg_diag_internal_reason
from findings
cross join coverage
order by findings.sampled_relpages desc, findings.role_name
