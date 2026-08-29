with sessions as (
  select
    a.pid,
    a.usename,
    a.client_addr,
    s.ssl,
    s.version as tls_version,
    s.cipher as tls_cipher,
    s.bits as tls_bits,
    null::boolean as gss_encrypted
  from pg_catalog.pg_stat_activity a
  left join pg_catalog.pg_stat_ssl s on s.pid = a.pid
  where coalesce(a.backend_type, 'client backend') = 'client backend'
    and a.usename is not null
),
classified as (
  select
    s.*,
    (s.client_addr is not null and (s.client_addr <<= '127.0.0.0/8'::inet or s.client_addr = '::1'::inet)) as is_loopback
  from sessions s
),
per_role_bounded as (
  select
    c.usename,
    count(*)::int8 as session_count,
    count(*) filter (where c.ssl)::int8 as tls_session_count,
    null::int8 as gss_encrypted_session_count,
    count(*) filter (where c.client_addr is null)::int8 as local_socket_session_count,
    count(*) filter (where c.is_loopback)::int8 as loopback_session_count,
    count(*) filter (
      where c.client_addr is not null and not c.is_loopback and c.ssl = false
    )::int8 as remote_unencrypted_session_count,
    count(*) filter (where c.client_addr is not null and c.ssl is null)::int8 as encryption_unknown_session_count,
    string_agg(distinct c.tls_version, ', ') as tls_versions,
    string_agg(distinct c.tls_cipher, ', ') as tls_ciphers,
    min(c.tls_bits)::int8 as min_tls_cipher_bits
  from classified c
  group by c.usename
  order by session_count desc, c.usename
  limit 1001
),
per_role as (
  select * from per_role_bounded limit 1000
),
coverage as (
  select (select count(*) > 1000 from per_role_bounded) as result_truncated
)
select
  p.usename::text as role_name,
  r.oid::int8 as role_oid,
  coalesce(r.rolsuper, false) as superuser,
  p.session_count,
  p.tls_session_count,
  p.gss_encrypted_session_count,
  p.local_socket_session_count,
  p.loopback_session_count,
  p.remote_unencrypted_session_count,
  p.encryption_unknown_session_count,
  p.tls_versions,
  p.tls_ciphers,
  p.min_tls_cipher_bits,
  coverage.result_truncated,
  case
    when p.remote_unencrypted_session_count > 0 then 'medium'
    when p.encryption_unknown_session_count > 0 then 'unknown'
    else 'ok'
  end as risk_level,
  case
    when p.remote_unencrypted_session_count > 0
      then 'Role has non-loopback TCP sessions without TLS encryption'
    when p.encryption_unknown_session_count > 0
      then 'TLS state of other roles is hidden; grant pg_read_all_stats to the collector role for complete evidence'
    else ''
  end as risk_reason
from per_role p
left join pg_catalog.pg_roles r on r.rolname = p.usename
cross join coverage
union all
select
  '[coverage]'::text, null::int8, false, 0::int8, 0::int8, null::int8, 0::int8, 0::int8, 0::int8, 0::int8, null::text, null::text, null::int8,
  true, 'unknown'::text,
  'More than 1000 roles have sessions; findings above are proven but the list is incomplete'::text
from coverage
where coverage.result_truncated
order by session_count desc, role_name
