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

## Checklist
- Compare with connection pressure.
- Check pooler behavior.
- Use external NIC counters for drops/errors.
