with policies_bounded as (
  select
    p.oid,
    p.polname,
    p.polrelid,
    p.polcmd,
    p.polpermissive,
    p.polroles,
    (p.polqual is not null) as has_using,
    (p.polwithcheck is not null) as has_with_check
  from pg_catalog.pg_policy p
  order by p.polrelid, p.polname, p.oid
  limit 3001
),
policies as (
  select * from policies_bounded limit 3000
),
coverage as (
  select (select count(*) > 3000 from policies_bounded) as result_truncated
)
select
  n.nspname::text as schema_name,
  c.relname::text as table_name,
  pg_catalog.pg_get_userbyid(c.relowner)::text as table_owner,
  c.relrowsecurity as rls_enabled,
  c.relforcerowsecurity as rls_forced,
  p.polname::text as policy_name,
  case p.polcmd
    when '*' then 'ALL'
    when 'r' then 'SELECT'
    when 'a' then 'INSERT'
    when 'w' then 'UPDATE'
    when 'd' then 'DELETE'
    else p.polcmd::text
  end as command,
  case when p.polpermissive then 'permissive' else 'restrictive' end as policy_type,
  case
    when p.polroles = '{0}'::oid[] then 'PUBLIC'
    else (
      select string_agg(r.rolname::text, ', ' order by r.rolname)
      from unnest(p.polroles) u(role_oid)
      join pg_catalog.pg_roles r on r.oid = u.role_oid
    )
  end as applies_to_roles,
  p.has_using,
  p.has_with_check,
  coverage.result_truncated,
  case when coverage.result_truncated then 'unknown' else 'ok' end as pg_diag_internal_severity,
  case
    when coverage.result_truncated
      then 'More than 3000 row-level security policies exist; the list is partial'
    else ''
  end as pg_diag_internal_reason
from policies p
join pg_catalog.pg_class c on c.oid = p.polrelid
join pg_catalog.pg_namespace n on n.oid = c.relnamespace
cross join coverage
order by schema_name, table_name, policy_name
