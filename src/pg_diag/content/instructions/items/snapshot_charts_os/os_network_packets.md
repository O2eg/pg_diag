# Network Packets

This instruction belongs to report item `snapshot_charts_os.os_network_packets`. The item is backed by `os.network_packets` (snapshot metric).

## What this item shows
- Packet rate by interface over time.
- Small-packet or high-connection network behavior during snapshots.

## What to watch
- Very high packet rate without high throughput.
- Packet spikes during connection storms.
- Unexpected interface carrying traffic.

## Common fault causes
- Chatty application protocol.
- Connection churn.
- Monitoring bursts.
- Network retries.

## Automatic evaluation
- Receive and transmit packet rates are stacked per interface and use the same packets/second unit.
- Loopback is excluded and counter rollback becomes missing data rather than zero.

## Related report items
- [activity_locks.connection_pressure](#item-activity_locks.connection_pressure) — Check whether connection churn drives packet rate.
- [os.sysctl_tcp](#item-os.sysctl_tcp) — Review TCP queue and timeout settings.
- [os.network_addresses](#item-os.network_addresses) — Identify interfaces carrying database traffic.

## Checklist
- Compare with connection pressure.
- Check pooler behavior.
- Use external NIC counters for drops/errors.
