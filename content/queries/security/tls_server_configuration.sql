with settings as (
  select
    max(setting) filter (where name = 'ssl') as ssl,
    max(setting) filter (where name = 'ssl_min_protocol_version') as ssl_min_protocol_version,
    max(setting) filter (where name = 'ssl_cert_file') as ssl_cert_file,
    max(setting) filter (where name = 'ssl_key_file') as ssl_key_file,
    bool_or(name = 'ssl_min_protocol_version') as has_ssl_min_protocol_version
  from pg_catalog.pg_settings
  where name in ('ssl', 'ssl_min_protocol_version', 'ssl_cert_file', 'ssl_key_file')
)
select
  'ssl' as check_name,
  coalesce(ssl, '<missing>') as current_value,
  'on' as expected_value,
  'high' as risk_level,
  'server-side TLS is disabled' as risk_reason
from settings
where coalesce(ssl, 'off') <> 'on'

union all

select
  'ssl_min_protocol_version' as check_name,
  coalesce(ssl_min_protocol_version, '<missing>') as current_value,
  'TLSv1.2 or newer' as expected_value,
  case
    when ssl_min_protocol_version in ('TLSv1', 'TLSv1.1') then 'high'
    else 'medium'
  end as risk_level,
  'TLS minimum protocol version is weaker than TLSv1.2 or not enforced' as risk_reason
from settings
where ssl = 'on'
  and (
    not has_ssl_min_protocol_version
    or coalesce(ssl_min_protocol_version, '') in ('', 'TLSv1', 'TLSv1.1')
  )

union all

select
  'ssl_cert_file' as check_name,
  coalesce(nullif(ssl_cert_file, ''), '<empty>') as current_value,
  'configured certificate file' as expected_value,
  'medium' as risk_level,
  'ssl is enabled but ssl_cert_file is empty' as risk_reason
from settings
where ssl = 'on'
  and coalesce(ssl_cert_file, '') = ''

union all

select
  'ssl_key_file' as check_name,
  coalesce(nullif(ssl_key_file, ''), '<empty>') as current_value,
  'configured private key file' as expected_value,
  'medium' as risk_level,
  'ssl is enabled but ssl_key_file is empty' as risk_reason
from settings
where ssl = 'on'
  and coalesce(ssl_key_file, '') = ''
order by check_name asc
