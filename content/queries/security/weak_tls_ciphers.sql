with cipher_setting as (
  select setting
  from pg_catalog.pg_settings
  where name = 'ssl_ciphers'
),
tokens as (
  select
    setting,
    btrim(token) as cipher_class
  from cipher_setting
  cross join lateral regexp_split_to_table(setting, ':') as token
),
findings as (
  select
    setting as ssl_ciphers,
    cipher_class,
    case
      when upper(cipher_class) in ('LOW', 'EXP', 'EXPORT', 'NULL', 'ENULL', 'ANULL', 'MD5', 'RC4', 'DES')
        or upper(cipher_class) like '%3DES%'
        then 'high'
      when upper(cipher_class) = 'MEDIUM' then 'medium'
      else 'ok'
    end as risk_level
  from tokens
  where cipher_class <> ''
    and left(cipher_class, 1) not in ('!', '-')
)
select
  ssl_ciphers,
  cipher_class,
  risk_level,
  case
    when risk_level = 'high' then 'ssl_ciphers allows weak or anonymous TLS cipher classes'
    when risk_level = 'medium' then 'ssl_ciphers allows medium-strength TLS cipher classes'
    else 'informational TLS cipher token'
  end as risk_reason
from findings
where risk_level <> 'ok'
order by
  risk_level desc,
  cipher_class asc
