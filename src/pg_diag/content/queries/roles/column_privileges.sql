with table_roots_bounded as (
  select c.oid, c.relname, c.relowner, n.nspname,
    greatest(coalesce(c.relpages, 0), 0)::int8 as relpages
  from pg_catalog.pg_class c
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where c.relkind in ('r', 'p', 'v', 'm', 'f')
    and n.nspname not in ('pg_catalog', 'information_schema')
    and n.nspname not like 'pg_toast%'
  order by c.relpages desc, n.nspname, c.relname, c.oid
  limit 5001
),
table_candidates as (
  select * from table_roots_bounded limit 5000
),
column_roots_bounded as (
  select t.oid, t.nspname, t.relname, t.relowner, t.relpages, a.attname, a.attnum, a.attacl
  from table_candidates t
  join pg_catalog.pg_attribute a on a.attrelid = t.oid
  where a.attnum > 0
    and not a.attisdropped
    and a.attacl is not null
  order by t.relpages desc, t.nspname, t.relname, a.attnum
  limit 3001
),
column_candidates as (
  select * from column_roots_bounded limit 3000
),
grants_bounded as (
  select
    c.oid,
    c.nspname,
    c.relname,
    c.relowner,
    c.relpages,
    c.attname,
    c.attnum,
    g.grantee,
    g.privileges,
    g.grantable_privileges,
    g.grantors
  from column_candidates c
  cross join lateral (
    select
      e.grantee,
      string_agg(e.privilege_type, ', ' order by e.privilege_type) as privileges,
      string_agg(e.privilege_type, ', ' order by e.privilege_type)
        filter (where e.is_grantable) as grantable_privileges,
      string_agg(distinct pg_catalog.pg_get_userbyid(e.grantor)::text, ', ') as grantors
    from aclexplode(c.attacl) e
    where e.grantee <> c.relowner
    group by e.grantee
  ) g
  order by c.relpages desc, c.nspname, c.relname, c.attnum, g.grantee
  limit 3001
),
grants as (
  select * from grants_bounded limit 3000
),
coverage as (
  select
    (select count(*) > 5000 from table_roots_bounded) as candidate_sample_truncated,
    (select count(*) > 3000 from column_roots_bounded) as column_sample_truncated,
    (select count(*) > 3000 from grants_bounded) as result_truncated
)
select
  g.nspname::text as schema_name,
  g.relname::text as relation_name,
  g.oid::int8 as relation_oid,
  g.attname::text as column_name,
  pg_catalog.pg_get_userbyid(g.relowner)::text as owner_name,
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
  coverage.column_sample_truncated,
  coverage.result_truncated,
  case
    when coverage.candidate_sample_truncated or coverage.column_sample_truncated or coverage.result_truncated
      then 'unknown'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when coverage.candidate_sample_truncated
      then 'Only the 5000 largest relations were inspected for column privileges; smaller relations are not covered'
    when coverage.column_sample_truncated or coverage.result_truncated
      then 'More than 3000 column privilege rows exist; the list is partial'
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
  ''::text,
  ''::text,
  null::text,
  null::text,
  null::text,
  coverage.candidate_sample_truncated,
  coverage.column_sample_truncated,
  coverage.result_truncated,
  'unknown'::text,
  'Only the 5000 largest relations were inspected for column privileges; an empty result is not a clean result'::text
from coverage
where coverage.candidate_sample_truncated or coverage.column_sample_truncated or coverage.result_truncated
order by schema_name, relation_name, column_name, grantee_name
