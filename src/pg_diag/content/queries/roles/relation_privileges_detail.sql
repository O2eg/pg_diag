with storage_relation_roots_bounded as (
  select c.oid, c.relkind, c.relname, c.relowner, c.relacl, n.nspname,
    greatest(coalesce(c.relpages, 0), 0)::int8 as relpages
  from pg_catalog.pg_class c
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where c.relacl is not null
    and c.relkind in ('r', 'm')
    and greatest(coalesce(c.relpages, 0), 0) > 0
    and n.nspname not in ('pg_catalog', 'information_schema')
    and n.nspname not like 'pg_toast%'
  order by c.relpages desc, n.nspname, c.relname, c.oid
  limit 3001
),
storage_relation_candidates as (
  select * from storage_relation_roots_bounded limit 3000
),
named_relation_roots_bounded as (
  select c.oid, c.relkind, c.relname, c.relowner, c.relacl, n.nspname, 0::int8 as relpages
  from pg_catalog.pg_class c
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where c.relacl is not null
    and (
      c.relkind in ('p', 'S', 'v', 'f')
      or (c.relkind in ('r', 'm') and greatest(coalesce(c.relpages, 0), 0) = 0)
    )
    and n.nspname not in ('pg_catalog', 'information_schema')
    and n.nspname not like 'pg_toast%'
  order by n.nspname, c.relname, c.oid
  limit 3001
),
named_relation_candidates as (
  select * from named_relation_roots_bounded limit 3000
),
relation_candidates as (
  select * from storage_relation_candidates
  union all
  select * from named_relation_candidates
),
grants_bounded as (
  select
    c.oid,
    c.nspname,
    c.relname,
    c.relkind,
    c.relowner,
    c.relpages,
    g.grantee,
    g.privileges,
    g.grantable_privileges,
    g.grantors
  from relation_candidates c
  cross join lateral (
    select
      e.grantee,
      string_agg(e.privilege_type, ', ' order by e.privilege_type) as privileges,
      string_agg(e.privilege_type, ', ' order by e.privilege_type)
        filter (where e.is_grantable) as grantable_privileges,
      string_agg(distinct pg_catalog.pg_get_userbyid(e.grantor)::text, ', ') as grantors
    from aclexplode(c.relacl) e
    where e.grantee <> c.relowner
    group by e.grantee
  ) g
  order by c.relpages desc, c.nspname, c.relname, g.grantee
  limit 3001
),
grants as (
  select * from grants_bounded limit 3000
),
coverage as (
  select
    (
      (select count(*) > 3000 from storage_relation_roots_bounded)
      or (select count(*) > 3000 from named_relation_roots_bounded)
    ) as candidate_sample_truncated,
    (select count(*) > 3000 from grants_bounded) as result_truncated
)
select
  g.nspname::text as schema_name,
  g.relname::text as relation_name,
  g.oid::int8 as relation_oid,
  case g.relkind
    when 'r' then 'table'
    when 'p' then 'partitioned table'
    when 'v' then 'view'
    when 'm' then 'materialized view'
    when 'f' then 'foreign table'
    when 'S' then 'sequence'
    else g.relkind::text
  end as object_kind,
  pg_catalog.pg_get_userbyid(g.relowner)::text as owner_name,
  g.relpages,
  coalesce(gr.rolname::text, 'PUBLIC') as grantee_name,
  case
    when gr.oid is null then 'PUBLIC'
    when gr.rolcanlogin then 'login role'
    else 'group role'
  end as grantee_kind,
  g.privileges,
  g.grantable_privileges,
  g.grantors,
  coverage.candidate_sample_truncated,
  coverage.result_truncated,
  case
    when coverage.candidate_sample_truncated or coverage.result_truncated then 'unknown'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when coverage.candidate_sample_truncated
      then 'Relation candidate pools were truncated; the detail covers only the sampled relations'
    when coverage.result_truncated
      then 'More than 3000 relation/grantee rows exist; the detail is partial'
    else ''
  end as pg_diag_internal_reason
from grants g
left join pg_catalog.pg_roles gr on gr.oid = g.grantee
cross join coverage
union all
select
  '[coverage]'::text,
  ''::text,
  null::int8,
  ''::text,
  ''::text,
  0::int8,
  ''::text,
  ''::text,
  null::text,
  null::text,
  null::text,
  coverage.candidate_sample_truncated,
  coverage.result_truncated,
  'unknown'::text,
  'The bounded relation candidate or result sample was truncated; an empty result is not a clean result'::text
from coverage
where coverage.candidate_sample_truncated or coverage.result_truncated
order by relpages desc, schema_name, relation_name, grantee_name
