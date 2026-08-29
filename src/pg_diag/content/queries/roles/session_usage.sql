with sessions as (
  select
    a.usename,
    a.datname,
    a.state,
    a.backend_start,
    a.xact_start,
    a.client_addr,
    a.application_name
  from pg_catalog.pg_stat_activity a
  where coalesce(a.backend_type, 'client backend') = 'client backend'
    and a.usename is not null
),
per_role_bounded as (
  select
    s.usename,
    count(*)::int8 as session_count,
    count(*) filter (where s.state = 'active')::int8 as active_count,
    count(*) filter (where s.state = 'idle')::int8 as idle_count,
    count(*) filter (
      where s.state in ('idle in transaction', 'idle in transaction (aborted)')
    )::int8 as idle_in_transaction_count,
    count(*) filter (where s.state is null)::int8 as state_hidden_count,
    count(distinct s.datname)::int8 as database_count,
    count(distinct s.client_addr)::int8 as client_address_count,
    count(*) filter (where s.client_addr is null)::int8 as local_socket_session_count,
    left(string_agg(distinct nullif(s.application_name, ''), ', '), 500) as application_names,
    max(extract(epoch from (now() - s.backend_start)))::float8 as oldest_session_age_seconds,
    max(extract(epoch from (now() - s.xact_start)))::float8 as longest_transaction_age_seconds
  from sessions s
  group by s.usename
  order by session_count desc, s.usename
  limit 1001
),
per_role as (
  select * from per_role_bounded limit 1000
),
coverage as (
  select (select count(*) > 1000 from per_role_bounded) as result_truncated
),
findings as (
  select
    p.usename::text as role_name,
    r.oid::int8 as role_oid,
    coalesce(r.rolsuper, false) as superuser,
    r.rolconnlimit as connection_limit,
    p.session_count,
    case
      when r.rolconnlimit > 0 then (p.session_count * 100.0 / r.rolconnlimit)::float8
      else null
    end as limit_utilization_pct,
    p.active_count,
    p.idle_count,
    p.idle_in_transaction_count,
    p.state_hidden_count,
    p.database_count,
    p.client_address_count,
    p.local_socket_session_count,
    p.application_names,
    p.oldest_session_age_seconds,
    p.longest_transaction_age_seconds
  from per_role p
  left join pg_catalog.pg_roles r on r.rolname = p.usename
)
select
  f.*,
  coverage.result_truncated,
  case
    when f.limit_utilization_pct >= 90 then 'medium'
    when f.connection_limit = 0 then 'medium'
    when f.state_hidden_count > 0 then 'unknown'
    else 'ok'
  end as risk_level,
  case
    when f.limit_utilization_pct >= 90
      then 'Role sessions use at least 90 percent of the per-role connection limit'
    when f.connection_limit = 0
      then 'Role has sessions although its connection limit is zero; existing sessions predate the limit'
    when f.state_hidden_count > 0
      then 'Session states of other roles are hidden; grant pg_read_all_stats to the collector role for complete state counts'
    else ''
  end as risk_reason
from findings f
cross join coverage
union all
select
  '[coverage]'::text, null::int8, false, null::int4, 0::int8, null::float8, 0::int8, 0::int8, 0::int8, 0::int8, 0::int8, 0::int8, 0::int8,
  null::text, null::float8, null::float8, true, 'unknown'::text,
  'More than 1000 roles have sessions; findings above are proven but the list is incomplete'::text
from coverage
where coverage.result_truncated
order by session_count desc, role_name
