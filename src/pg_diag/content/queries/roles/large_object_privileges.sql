with large_object_roots_bounded as (
  select m.oid, m.lomowner, m.lomacl::text as acl_signature
  from pg_catalog.pg_largeobject_metadata m
  where m.lomacl is not null
  order by m.oid
  limit 10001
),
large_object_candidates as (
  select * from large_object_roots_bounded limit 10000
),
acl_groups as (
  select
    lomowner,
    acl_signature,
    min(oid) as sample_oid,
    count(*)::int8 as object_count
  from large_object_candidates
  group by lomowner, acl_signature
),
grants_bounded as (
  select
    g.lomowner,
    g.object_count,
    e.grantee,
    e.privilege_type,
    e.is_grantable
  from acl_groups g
  cross join lateral aclexplode(
    (select m.lomacl from pg_catalog.pg_largeobject_metadata m where m.oid = g.sample_oid)
  ) e
  where e.grantee <> g.lomowner
  limit 3001
),
grants as (
  select * from grants_bounded limit 3000
),
ranked_findings as (
  select
    pg_catalog.pg_get_userbyid(g.lomowner)::text as owner_name,
    coalesce(gr.rolname::text, 'PUBLIC') as grantee_name,
    case
      when gr.oid is null then 'PUBLIC'
      when gr.rolcanlogin then 'login role'
      else 'group role'
    end as grantee_kind,
    g.privilege_type,
    sum(g.object_count)::int8 as object_count,
    coalesce(sum(g.object_count) filter (where g.is_grantable), 0)::int8 as grantable_object_count
  from grants g
  left join pg_catalog.pg_roles gr on gr.oid = g.grantee
  group by g.lomowner, gr.oid, gr.rolname, gr.rolcanlogin, g.privilege_type
  order by owner_name, grantee_name, g.privilege_type
  limit 3001
),
settings as (
  select (current_setting('lo_compat_privileges') = 'on') as lo_compat_privileges
),
coverage as (
  select
    (select count(*) > 10000 from large_object_roots_bounded) as candidate_sample_truncated,
    (select count(*) > 3000 from grants_bounded) as acl_expansion_truncated,
    (select count(*) > 3000 from ranked_findings) as result_truncated
),
findings as (
  select * from ranked_findings limit 3000
)
select
  findings.owner_name,
  findings.grantee_name,
  findings.grantee_kind,
  findings.privilege_type,
  findings.object_count,
  findings.grantable_object_count,
  settings.lo_compat_privileges,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  coverage.result_truncated,
  case
    when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
      then 'unknown'
    when settings.lo_compat_privileges then 'medium'
    else 'ok'
  end as pg_diag_internal_severity,
  case
    when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
      then 'Large object candidate, ACL expansion, or result sample was truncated; privilege counts are partial'
    when settings.lo_compat_privileges
      then 'lo_compat_privileges is on: large object privilege checks are disabled and every role can read or modify any large object'
    else ''
  end as pg_diag_internal_reason
from findings
cross join settings
cross join coverage
union all
select
  '[coverage]'::text,
  ''::text,
  ''::text,
  ''::text,
  0::int8,
  0::int8,
  settings.lo_compat_privileges,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  coverage.result_truncated,
  'unknown'::text,
  'Large object candidate, ACL expansion, or result sample was truncated; an empty result is not a clean result'::text
from settings
cross join coverage
where coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
union all
select
  '[lo_compat_privileges]'::text,
  'PUBLIC'::text,
  'PUBLIC'::text,
  'ALL'::text,
  null::int8,
  null::int8,
  settings.lo_compat_privileges,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  coverage.result_truncated,
  'medium'::text,
  'lo_compat_privileges is on: large object privilege checks are disabled and every role can read or modify any large object'::text
from settings
cross join coverage
where settings.lo_compat_privileges
order by owner_name, grantee_name, privilege_type
