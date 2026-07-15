# Network Transmit Throughput

This instruction belongs to report item `snapshot_charts_os.os_network_transmit`. The item is backed by `os.network_transmit_throughput` (snapshot metric).

## What this item shows
- Outbound network throughput by interface over time.
- Network send pressure during query results, replication, or backup streaming.

## What to watch
- Transmit spikes from large result sets.
- Replication network saturation.
- Unexpected traffic from database host.

## Common fault causes
- Large client result sets.
- WAL streaming.
- Backup export.
- Monitoring or log shipping.

## Automatic evaluation
- Rates are counter deltas over monotonic elapsed time; counter rollback becomes missing data rather than zero.
- The loopback interface is intentionally excluded.

## Checklist
- Compare with client wait events and replication sender lag.
- Map interface to workload path.
- Check network errors outside pg_diag when throughput looks capped.
