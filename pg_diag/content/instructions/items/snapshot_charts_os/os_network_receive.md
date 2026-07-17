# Network Receive Throughput

This instruction belongs to report item `snapshot_charts_os.os_network_receive`. The item is backed by `os.network_receive_throughput` (snapshot metric).

## What this item shows
- Inbound network throughput by interface over time.
- Network receive pressure during client, replication, or backup traffic.

## Units
- `B/s` means bytes received per wall-clock second. The chart uses adaptive IEC rate units such as `KiB/s`, `MiB/s`, or `GiB/s`.

## What to watch
- Receive spikes during replication or bulk load.
- Unexpected traffic on database host.
- Flatline or missing data for expected active interface.

## Common fault causes
- Client traffic burst.
- Replica catch-up.
- Backup restore.
- Wrong interface monitored.

## Automatic evaluation
- Rates are counter deltas over monotonic elapsed time; counter rollback becomes missing data rather than zero.
- The loopback interface is intentionally excluded, so local TCP traffic may not appear.

## Checklist
- Map interface to client/replication network.
- Compare with replication lag and client waits.
- Check external network metrics for drops or errors.
