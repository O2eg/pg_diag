with function_roots_bounded as (
  select
    p.oid,
    p.proname,
    p.proowner,
    p.prosecdef,
    p.proconfig,
    p.prolang,
    p.proacl,
    n.nspname
  from pg_catalog.pg_proc p
  join pg_catalog.pg_namespace n on n.oid = p.pronamespace
  left join pg_catalog.pg_stat_user_functions s on s.funcid = p.oid
  where n.nspname not in ('pg_catalog', 'information_schema', 'pg_toast')
    and n.nspname not like 'pg_temp_%'
    and n.nspname not like 'pg_toast_temp_%'
  order by coalesce(s.calls, 0) desc, n.nspname, p.proname, p.oid
  limit 1001
),
function_roots as (
  select *
  from function_roots_bounded
  limit 1000
),
function_candidates as (
  select roots.*
  from function_roots roots
  where not exists (
    select 1
    from pg_catalog.pg_depend d
    where d.classid = 'pg_proc'::regclass
      and d.objid = roots.oid
      and d.deptype = 'e'
  )
),
function_acl_bounded as (
  select
    p.oid as function_oid,
    p.nspname::text as schema_name,
    p.proname::text as function_name,
    pg_catalog.pg_get_function_identity_arguments(p.oid) as function_signature,
    pg_catalog.pg_get_userbyid(p.proowner)::text as owner_name,
    p.prosecdef as is_security_definer,
    exists (
      select 1
      from unnest(coalesce(p.proconfig, array[]::text[])) as config(setting)
      where lower(setting) like 'search_path=%'
    ) as has_search_path_config,
    l.lanname::text as language_name,
    acl.grantor,
    acl.grantee,
    acl.privilege_type,
    acl.is_grantable
  from function_candidates p
  join pg_catalog.pg_language l on l.oid = p.prolang
  cross join lateral pg_catalog.aclexplode(
    coalesce(p.proacl, pg_catalog.acldefault('f', p.proowner))
  ) as acl
  where acl.privilege_type = 'EXECUTE'
    and (
      acl.grantee = 0
      or (acl.is_grantable and acl.grantee <> p.proowner)
    )
  limit 3001
),
function_acl as (
  select *
  from function_acl_bounded
  limit 3000
),
ranked_findings as (
  select *
  from function_acl
  order by schema_name, function_name, function_signature, grantee
  limit 1001
),
coverage as (
  select
    (select count(*) > 1000 from function_roots_bounded) as candidate_sample_truncated,
    (select count(*) > 3000 from function_acl_bounded) as acl_expansion_truncated,
    (select count(*) > 1000 from ranked_findings) as result_truncated
),
findings as (
  select *
  from ranked_findings
  limit 1000
)
select
  findings.function_oid,
  findings.schema_name,
  findings.function_name,
  findings.function_signature,
  findings.owner_name,
  case when findings.grantee = 0 then 'PUBLIC' else pg_catalog.pg_get_userbyid(findings.grantee)::text end as grantee,
  pg_catalog.pg_get_userbyid(findings.grantor)::text as grantor,
  findings.privilege_type,
  findings.is_grantable,
  findings.is_security_definer,
  findings.language_name,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  coverage.result_truncated,
  case
    when findings.grantee = 0 and findings.is_security_definer and not findings.has_search_path_config then 'high'
    when findings.grantee = 0 and findings.is_security_definer then 'medium'
    when findings.grantee = 0 then 'ok'
    when findings.is_grantable then 'medium'
    else 'ok'
  end as risk_level,
  case
    when coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
      then 'Function privilege finding is part of a truncated bounded sample; review coverage flags before treating the inventory as complete'
    when findings.grantee = 0 and findings.is_security_definer and not findings.has_search_path_config then 'PUBLIC can execute SECURITY DEFINER function without a function-local search_path'
    when findings.grantee = 0 and findings.is_security_definer then 'PUBLIC can execute SECURITY DEFINER function; review the function body and configured search_path'
    when findings.grantee = 0 then 'PUBLIC EXECUTE is the PostgreSQL default for functions; shown for inventory'
    when findings.is_grantable then 'function EXECUTE privilege can be granted onward'
    else 'informational function privilege'
  end as risk_reason
from findings
cross join coverage
union all
select
  null::oid,
  '[coverage]'::text,
  ''::text,
  ''::text,
  ''::text,
  ''::text,
  ''::text,
  ''::text,
  false,
  false,
  ''::text,
  coverage.candidate_sample_truncated,
  coverage.acl_expansion_truncated,
  coverage.result_truncated,
  'unknown'::text,
  'The bounded function candidate, ACL expansion, or result sample was truncated; absence of findings is not a clean result'::text
from coverage
where coverage.candidate_sample_truncated or coverage.acl_expansion_truncated or coverage.result_truncated
order by
  risk_level desc,
  schema_name asc,
  function_name asc,
  function_signature asc,
  grantee asc
