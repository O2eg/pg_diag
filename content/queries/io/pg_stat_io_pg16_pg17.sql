select /* pgwatch_generated */
    current_database() as datname,
    coalesce(backend_type, 'total') as backend_type,
    sum(coalesce(reads, 0))::int8 as reads,
    (sum(coalesce(reads, 0) * op_bytes) / 1048576.0)::int8 as read_bytes_mb,
    sum(coalesce(read_time, 0))::int8 as read_time_ms,
    sum(coalesce(writes, 0))::int8 as writes,
    (sum(coalesce(writes, 0) * op_bytes) / 1048576.0)::int8 as write_bytes_mb,
    sum(coalesce(write_time, 0))::int8 as write_time_ms,
    sum(coalesce(writebacks, 0))::int8 as writebacks,
    (sum(coalesce(writebacks, 0) * op_bytes) / 1048576.0)::int8 as writeback_bytes_mb,
    sum(coalesce(writeback_time, 0))::int8 as writeback_time_ms,
    sum(coalesce(fsyncs, 0))::int8 as fsyncs,
    sum(coalesce(fsync_time, 0))::int8 as fsync_time_ms,
    sum(coalesce(extends, 0))::int8 as extends,
    (sum(coalesce(extends, 0) * op_bytes) / 1048576.0)::int8 as extend_bytes_mb,
    sum(coalesce(hits, 0))::int8 as hits,
    sum(coalesce(evictions, 0))::int8 as evictions,
    sum(coalesce(reuses, 0))::int8 as reuses,
    max(extract(epoch from now() - stats_reset)::int) as stats_reset_s
from
    pg_stat_io
group by
    rollup (backend_type)
