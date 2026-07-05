select /* pgwatch_generated */
    statement_timestamp() as snapshot_time,
    pg_database.datname as datname,
    tmp2.application_name,
    tmp.state,
    coalesce(count,0) as count,
    coalesce(max_tx_duration,0) as max_tx_duration
from
  (
    values ('active'),
          ('idle'),
          ('idle in transaction'),
          ('idle in transaction (aborted)'),
          ('fastpath function call'),
          ('disabled')
  ) as tmp(state)
cross join pg_database
left join
  (
    select datname,
      application_name as application_name,
      state as state,
      count(*) as count,
      max(extract(epoch from now() - xact_start))::float as max_tx_duration
    from pg_stat_activity
    group by datname, application_name, state
  ) as tmp2
on tmp.state = tmp2.state and pg_database.datname = tmp2.datname
where pg_database.datname = current_database()
