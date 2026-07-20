with user_tables as (
  select
    c.oid,
    n.nspname as schema_name,
    c.relname as table_name,
    c.relkind,
    c.relrowsecurity as rls_enabled,
    c.relforcerowsecurity as rls_forced_for_owner
  from pg_catalog.pg_class c
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where c.relkind in ('r', 'p')
    and n.nspname not in ('pg_catalog', 'information_schema', 'pg_toast')
    and n.nspname not like 'pg_temp_%'
    and n.nspname not like 'pg_toast_temp_%'
),
policy_summary as (
  select
    p.polrelid,
    count(*)::int8 as policy_count,
    string_agg(
      p.polname || ' (' ||
      case p.polcmd
        when '*' then 'ALL'
        when 'r' then 'SELECT'
        when 'a' then 'INSERT'
        when 'w' then 'UPDATE'
        when 'd' then 'DELETE'
        else p.polcmd::text
      end || ')',
      ', ' order by p.polname
    ) as policies
  from pg_catalog.pg_policy p
  group by p.polrelid
)
select
  t.schema_name,
  t.table_name,
  case t.relkind when 'p' then 'partitioned table' else 'table' end as relation_kind,
  t.rls_enabled,
  t.rls_forced_for_owner,
  coalesce(ps.policy_count, 0) as policy_count,
  coalesce(ps.policies, '') as policies,
  case
    when coalesce(ps.policy_count, 0) > 0 and not t.rls_enabled then 'high'
    when t.rls_enabled and coalesce(ps.policy_count, 0) = 0 then 'ok'
    when t.rls_enabled and not t.rls_forced_for_owner then 'unknown'
    else 'ok'
  end as risk_level,
  case
    when coalesce(ps.policy_count, 0) > 0 and not t.rls_enabled then 'RLS policies exist but row level security is disabled'
    when t.rls_enabled and coalesce(ps.policy_count, 0) = 0 then 'RLS is enabled without policies, so the default-deny policy applies to non-bypass roles'
    when t.rls_enabled and not t.rls_forced_for_owner then 'RLS is not forced for the table owner; compare this expected PostgreSQL behavior with the security baseline'
    else 'RLS configuration is informational'
  end as risk_reason
from user_tables t
left join policy_summary ps on ps.polrelid = t.oid
where (coalesce(ps.policy_count, 0) > 0 and not t.rls_enabled)
   or (t.rls_enabled and coalesce(ps.policy_count, 0) = 0)
   or (t.rls_enabled and not t.rls_forced_for_owner)
order by
  risk_level desc,
  t.schema_name asc,
  t.table_name asc
limit 1000
