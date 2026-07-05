select
  database,
  gid,
  owner,
  transaction::text as transaction,
  prepared,
  extract(epoch from clock_timestamp() - prepared)::numeric(20, 3) as prepared_age_seconds,
  age(transaction)::int8 as xid_age
from pg_prepared_xacts
order by prepared_age_seconds desc
