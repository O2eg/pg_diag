with cipher_setting as (
  select
    setting,
    (select setting from pg_catalog.pg_settings where name = 'ssl') as ssl
  from pg_catalog.pg_settings
  where name = 'ssl_ciphers'
),
tokens as (
  select
    setting,
    ssl,
    btrim(token) as cipher_class
  from cipher_setting
  cross join lateral regexp_split_to_table(setting, ':') as token
),
findings as (
  select
    setting as ssl_ciphers,
    ssl,
    cipher_class,
    case
      when upper(cipher_class) in ('LOW', 'EXP', 'EXPORT', 'NULL', 'ENULL', 'ANULL', 'MD5', 'RC4', 'DES')
        or upper(cipher_class) like '%3DES%'
        then 'high'
      when upper(cipher_class) = 'MEDIUM' then 'medium'
      else 'ok'
    end as cipher_risk
  from tokens
  where cipher_class <> ''
    -- '!' and '-' remove ciphers, '+' only moves already-selected ciphers to the end of the
    -- list (PostgreSQL's default HIGH:MEDIUM:+3DES:!aNULL uses it to demote 3DES), and '@'
    -- tokens such as @STRENGTH control ordering; none of them adds a cipher class.
    and left(cipher_class, 1) not in ('!', '-', '+', '@')
)
select
  ssl_ciphers,
  ssl,
  cipher_class,
  case when ssl = 'on' then cipher_risk else 'unknown' end as risk_level,
  case
    when ssl <> 'on' and cipher_risk = 'high'
      then 'TLS is disabled (ssl=off), so the cipher policy is not in effect; the expression would allow weak or anonymous cipher classes once TLS is enabled'
    when ssl <> 'on'
      then 'TLS is disabled (ssl=off), so the cipher policy is not in effect; the expression would allow medium-strength cipher classes once TLS is enabled'
    when cipher_risk = 'high' then 'ssl_ciphers allows weak or anonymous TLS cipher classes'
    when cipher_risk = 'medium' then 'ssl_ciphers allows medium-strength TLS cipher classes'
    else 'informational TLS cipher token'
  end as risk_reason
from findings
where cipher_risk <> 'ok'
order by
  risk_level desc,
  cipher_class asc
