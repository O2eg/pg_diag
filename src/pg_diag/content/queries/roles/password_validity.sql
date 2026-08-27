with login_roles_bounded as (
  select
    r.oid,
    r.rolname,
    r.rolsuper,
    r.rolvaliduntil
  from pg_catalog.pg_roles r
  where r.rolcanlogin
    and r.rolname !~ '^pg_'
  order by r.rolname, r.oid
  limit 5001
),
login_roles as (
  select * from login_roles_bounded limit 5000
),
classified as (
  select
    r.rolname,
    r.rolsuper,
    r.rolvaliduntil,
    case
      when r.rolvaliduntil is null or r.rolvaliduntil = 'infinity' then 'no expiry'
      when r.rolvaliduntil < now() then 'expired'
      when r.rolvaliduntil < now() + interval '30 days' then 'expires within 30 days'
      else 'valid'
    end as validity_state
  from login_roles r
),
coverage as (
  select (select count(*) > 5000 from login_roles_bounded) as result_truncated
),
combined as (
select
  c.rolname::text as role_name,
  c.rolsuper as superuser,
  case when c.rolvaliduntil = 'infinity' then null else c.rolvaliduntil end as valid_until,
  c.validity_state,
  case
    when c.rolvaliduntil is null or c.rolvaliduntil = 'infinity' then null
    else floor(extract(epoch from (c.rolvaliduntil - now())) / 86400)::int8
  end as days_until_expiry,
  coverage.result_truncated,
  case
    when c.validity_state = 'expired' then 'medium'
    when c.validity_state = 'expires within 30 days' then 'unknown'
    when c.validity_state = 'no expiry' and c.rolsuper then 'unknown'
    else 'ok'
  end as risk_level,
  case
    when c.validity_state = 'expired'
      then 'Password validity has expired but the role still exists and can authenticate through non-password methods'
    when c.validity_state = 'expires within 30 days'
      then 'Password validity ends within 30 days; plan the rotation'
    when c.validity_state = 'no expiry' and c.rolsuper
      then 'Superuser login role has no password expiry'
    else ''
  end as risk_reason
from classified c
cross join coverage
union all
select
  '[coverage]'::text, false, null::timestamptz, 'unknown'::text, null::int8, true, 'unknown'::text,
  'More than 5000 login roles exist; findings above are proven but the list is incomplete'::text
from coverage
where coverage.result_truncated
)
select *
from combined
order by
  case validity_state
    when 'expired' then 0
    when 'expires within 30 days' then 1
    when 'valid' then 2
    else 3
  end,
  role_name
