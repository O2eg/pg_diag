with storage_relation_roots_bounded as (
  select c.oid, c.relkind, c.relowner, c.relacl::text as acl_signature, n.nspname
  from pg_catalog.pg_class c
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where c.relacl is not null
    and c.relkind in ('r', 'm')
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
  select c.oid, c.relkind, c.relowner, c.relacl::text as acl_signature, n.nspname
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
  limit 10001
),
named_relation_candidates as (
  select * from named_relation_roots_bounded limit 10000
),
relation_candidates as (
  select * from storage_relation_candidates
  union all
  select * from named_relation_candidates
),
relation_acl_groups as (
  select
    nspname,
    relkind,
    relowner,
    acl_signature,
    min(oid) as sample_oid,
    count(*)::int8 as object_count
  from relation_candidates
  group by nspname, relkind, relowner, acl_signature
),
relation_grants_bounded as (
  select
    g.nspname,
    case g.relkind
      when 'r' then 'table'
      when 'p' then 'partitioned table'
      when 'v' then 'view'
      when 'm' then 'materialized view'
      when 'f' then 'foreign table'
      when 'S' then 'sequence'
      else g.relkind::text
    end as object_kind,
    g.object_count,
    e.grantee,
    e.privilege_type,
    e.is_grantable
  from relation_acl_groups g
  cross join lateral aclexplode(
    (select c.relacl from pg_catalog.pg_class c where c.oid = g.sample_oid)
  ) e
  where e.grantee <> g.relowner
  limit 3001
),
relation_grants as (
  select * from relation_grants_bounded limit 3000
),
function_roots_bounded as (
  select p.oid, p.proowner, p.proacl::text as acl_signature, n.nspname
  from pg_catalog.pg_proc p
  join pg_catalog.pg_namespace n on n.oid = p.pronamespace
  left join pg_catalog.pg_stat_user_functions s on s.funcid = p.oid
  where p.proacl is not null
    and n.nspname not in ('pg_catalog', 'information_schema')
    and n.nspname not like 'pg_toast%'
  order by coalesce(s.calls, 0) desc, n.nspname, p.proname, p.oid
  limit 1001
),
function_candidates as (
  select * from function_roots_bounded limit 1000
),
function_acl_groups as (
  select
    nspname,
    proowner,
    acl_signature,
    min(oid) as sample_oid,
    count(*)::int8 as object_count
  from function_candidates
  group by nspname, proowner, acl_signature
),
function_grants_bounded as (
  select
    g.nspname,
    'function'::text as object_kind,
    g.object_count,
    e.grantee,
    e.privilege_type,
    e.is_grantable
  from function_acl_groups g
  cross join lateral aclexplode(
    (select p.proacl from pg_catalog.pg_proc p where p.oid = g.sample_oid)
  ) e
  where e.grantee <> g.proowner
  limit 3001
),
function_grants as (
  select * from function_grants_bounded limit 3000
),
type_roots_bounded as (
  select t.oid, t.typowner, t.typtype, t.typacl::text as acl_signature, n.nspname
  from pg_catalog.pg_type t
  join pg_catalog.pg_namespace n on n.oid = t.typnamespace
  where t.typacl is not null
    and t.typtype in ('b', 'd', 'e', 'r', 'm')
    and n.nspname not in ('pg_catalog', 'information_schema')
    and n.nspname not like 'pg_toast%'
  order by n.nspname, t.typname, t.oid
  limit 1001
),
type_candidates as (
  select * from type_roots_bounded limit 1000
),
type_acl_groups as (
  select
    nspname,
    typtype,
    typowner,
    acl_signature,
    min(oid) as sample_oid,
    count(*)::int8 as object_count
  from type_candidates
  group by nspname, typtype, typowner, acl_signature
),
type_grants_bounded as (
  select
    g.nspname,
    case g.typtype when 'd' then 'domain' else 'type' end as object_kind,
    g.object_count,
    e.grantee,
    e.privilege_type,
    e.is_grantable
  from type_acl_groups g
  cross join lateral aclexplode(
    (select t.typacl from pg_catalog.pg_type t where t.oid = g.sample_oid)
  ) e
  where e.grantee <> g.typowner
  limit 3001
),
type_grants as (
  select * from type_grants_bounded limit 3000
),
explicit_grants as (
  select * from relation_grants
  union all
  select * from function_grants
  union all
  select * from type_grants
),
ranked_findings as (
  select
    coalesce(gr.rolname::text, 'PUBLIC') as grantee_name,
    case
      when gr.oid is null then 'PUBLIC'
      when gr.rolcanlogin then 'login role'
      else 'group role'
    end as grantee_kind,
    coalesce(gr.rolsuper, false) as grantee_is_superuser,
    g.nspname::text as schema_name,
    g.object_kind,
    g.privilege_type,
    sum(g.object_count)::int8 as object_count,
    coalesce(sum(g.object_count) filter (where g.is_grantable), 0)::int8 as grantable_object_count
  from explicit_grants g
  left join pg_catalog.pg_roles gr on gr.oid = g.grantee
  group by gr.oid, gr.rolname, gr.rolcanlogin, gr.rolsuper, g.nspname, g.object_kind, g.privilege_type
  order by grantee_kind, grantee_name, schema_name, object_kind, privilege_type
  limit 3001
),
coverage as (
  select
    (
      (select count(*) > 10000 from storage_relation_roots_bounded)
      or (select count(*) > 10000 from named_relation_roots_bounded)
      or (select count(*) > 1000 from function_roots_bounded)
      or (select count(*) > 1000 from type_roots_bounded)
    ) as candidate_sample_truncated,
    (
      (select count(*) > 3000 from relation_grants_bounded)
      or (select count(*) > 3000 from function_grants_bounded)
      or (select count(*) > 3000 from type_grants_bounded)
    ) as acl_expansion_truncated,
    (select count(*) > 3000 from ranked_findings) as result_truncated
),
findings as (
  select * from ranked_findings limit 3000
)
select
  findings.grantee_name,
  findings.grantee_kind,
  findings.grantee_is_superuser,
  findings.schema_name,
  findings.object_kind,
  findings.privilege_type,
  findings.object_count,
  findings.grantable_object_count,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  coverage.result_truncated,
  case
    when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
      then 'unknown'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when coverage.candidate_sample_truncated
      then 'Object candidate pools were truncated; privilege counts cover only the sampled objects'
    when coverage.acl_expansion_truncated
      then 'ACL expansion was truncated; privilege counts are partial'
    when coverage.result_truncated
      then 'More than 3000 grantee/schema/privilege combinations exist; the matrix is partial'
    else ''
  end as pg_diag_internal_reason
from findings
cross join coverage
union all
select
  '[coverage]'::text,
  ''::text,
  false,
  ''::text,
  ''::text,
  ''::text,
  0::int8,
  0::int8,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  coverage.result_truncated,
  'unknown'::text,
  'The bounded object candidate, ACL expansion, or result sample was truncated; an empty matrix is not a clean result'::text
from coverage
where coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
order by grantee_kind, grantee_name, schema_name, object_kind, privilege_type
