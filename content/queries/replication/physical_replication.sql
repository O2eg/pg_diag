select /* pgwatch_generated */
  current_database() as datname,
  application_name as application_name,
  (pg_current_wal_lsn() - '0/0') % (2^52)::bigint as current_wal_lsn,
  (sent_lsn - '0/0') % (2^52)::bigint as sent_lsn,
  (write_lsn - '0/0') % (2^52)::bigint as write_lsn,
  (flush_lsn - '0/0') % (2^52)::bigint as flush_lsn,
  (replay_lsn - '0/0') % (2^52)::bigint as replay_lsn,
  extract(seconds from (now() - reply_time)) reply_time_lag
from pg_stat_replication
