with eol_dates(major_version, eol_date) as (
  values
    (10, date '2022-11-10'),
    (11, date '2023-11-09'),
    (12, date '2024-11-14'),
    (13, date '2025-11-13'),
    (14, date '2026-11-12'),
    (15, date '2027-11-11'),
    (16, date '2028-11-09'),
    (17, date '2029-11-08'),
    (18, date '2030-11-14')
),
server as (
  select
    current_setting('server_version') as server_version,
    (current_setting('server_version_num')::int / 10000) as major_version
)
select
  server.server_version,
  server.major_version::int8 as major_version,
  eol.eol_date,
  case when eol.eol_date is null then null
    else (eol.eol_date - current_date)::int8 end as days_to_eol,
  case
    when eol.eol_date is null then 'unknown'
    when eol.eol_date < current_date then 'high'
    when eol.eol_date - current_date < 365 then 'medium'
    else 'ok'
  end as risk_level,
  case
    when eol.eol_date is null
      then 'No end-of-life date is known for this major version; check postgresql.org/support/versioning'
    when eol.eol_date < current_date
      then 'This PostgreSQL major version reached end of life and no longer receives security or bug fixes'
    when eol.eol_date - current_date < 365
      then 'This PostgreSQL major version reaches end of life within a year; plan the upgrade'
    else ''
  end as risk_reason
from server
left join eol_dates eol on eol.major_version = server.major_version
order by server.major_version
limit 1
