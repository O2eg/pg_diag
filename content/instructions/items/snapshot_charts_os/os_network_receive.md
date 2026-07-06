# Network Receive Throughput

This instruction belongs to report item `snapshot_charts_os.os_network_receive`. The item is backed by `os.network_receive_throughput` (snapshot metric).

## What this item shows
- Inbound network throughput by interface over time.
- Network receive pressure during client, replication, or backup traffic.

## What to watch
- Receive spikes during replication or bulk load.
- Unexpected traffic on database host.
- Flatline or missing data for expected active interface.

## Common fault causes
- Client traffic burst.
- Replica catch-up.
- Backup restore.
- Wrong interface monitored.

## Checklist
- Map interface to client/replication network.
- Compare with replication lag and client waits.
- Check external network metrics for drops or errors.
