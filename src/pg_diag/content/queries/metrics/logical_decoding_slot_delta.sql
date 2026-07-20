select
  statement_timestamp() as snapshot_time,
  slot_name,
  stats_reset,
  spill_txns::int8 as spill_txns,
  spill_count::int8 as spill_count,
  spill_bytes::int8 as spill_bytes,
  stream_txns::int8 as stream_txns,
  stream_count::int8 as stream_count,
  stream_bytes::int8 as stream_bytes,
  total_txns::int8 as total_txns,
  total_bytes::int8 as total_bytes
from pg_catalog.pg_stat_replication_slots
order by spill_bytes desc nulls last, slot_name
limit 50
