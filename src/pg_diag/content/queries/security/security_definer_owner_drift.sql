with function_roots_bounded as (
    select p.oid
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    join pg_roles r on r.oid = p.proowner
    left join pg_stat_user_functions stats on stats.funcid = p.oid
    where p.prosecdef
      and n.nspname not in ('pg_catalog', 'information_schema')
      and n.nspname not like 'pg_toast%'
      and (r.rolsuper or p.proowner <> n.nspowner)
    order by r.rolsuper desc, coalesce(stats.calls, 0) desc,
             n.nspname, p.proname, p.oid
    limit 1001
),
function_roots as (
    select * from function_roots_bounded limit 1000
),
function_candidates as (
    select roots.oid
    from function_roots roots
    where not exists (
        select 1 from pg_depend d
        where d.classid = 'pg_proc'::regclass
          and d.objid = roots.oid
          and d.deptype = 'e'
    )
),
coverage as (
  select
        (select count(*) > 1000 from function_roots_bounded) as candidate_sample_truncated
)
select
    n.nspname::text as schema_name,
    p.proname::text as function_name,
    p.oid::int8 as function_oid,
    pg_get_function_identity_arguments(p.oid) as function_arguments,
    pg_catalog.pg_get_userbyid(p.proowner)::text as function_owner,
    pg_catalog.pg_get_userbyid(n.nspowner)::text as schema_owner,
    r.rolsuper as owner_is_superuser,
    coverage.candidate_sample_truncated,
    case when r.rolsuper then 'high' else 'medium' end as risk_level,
    case
        when coverage.candidate_sample_truncated
            then 'SECURITY DEFINER owner finding is part of a truncated bounded sample; review the coverage flag before treating the inventory as complete'
        when r.rolsuper then 'SECURITY DEFINER function is owned by a superuser'
        else 'SECURITY DEFINER function owner differs from the containing schema owner'
    end as risk_reason
from function_candidates candidates
join pg_proc p on p.oid = candidates.oid
join pg_namespace n on n.oid = p.pronamespace
join pg_roles r on r.oid = p.proowner
cross join coverage
union all
select
    '[coverage]'::text,
    ''::text,
    null::int8,
    ''::text,
    ''::text,
    ''::text,
    false,
    coverage.candidate_sample_truncated,
    'unknown'::text,
    'The bounded SECURITY DEFINER candidate sample was truncated; functions outside the root may be missed, including when selected roots are later excluded as extension-owned'::text
from coverage
where coverage.candidate_sample_truncated
order by risk_level desc, schema_name, function_name
