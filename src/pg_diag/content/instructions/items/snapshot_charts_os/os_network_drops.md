# Network Interface Drops

This instruction belongs to report item `snapshot_charts_os.os_network_drops`. The item is backed by `os.network_drops` (snapshot metric).

## What this item shows

Receive and transmit drop rates per non-loopback interface from successive
`/proc/net/dev` samples. Units are packets/second. Counter rollback and missing
endpoints remain unknown. Older reports do not carry these counters.

## What to watch

- New drops, peaks and repeated drops on the interface carrying the workload.

## Common fault causes

RX drops can include unsupported protocols, filtering and missed packets;
`/proc/net/dev` combines some counters. TX drops may reflect resource shortages.
Drops do not automatically prove a broken cable, TCP retransmissions or packet
loss on the PostgreSQL path. Do not sum errors and drops as disjoint events.

## Automatic evaluation

The graph flags any observed drop for review and a peak of 100 drops per second
as critical triage; these are explicit heuristics, not universal capacity limits.

## Related report items

- [snapshot_charts_os.os_network_errors](#item-snapshot_charts_os.os_network_errors) — Separate interface errors from drops.
- [snapshot_charts_os.os_network_packets](#item-snapshot_charts_os.os_network_packets) — Compare packet volume on the same interface.
- [os.sysctl_tcp](#item-os.sysctl_tcp) — Inspect TCP buffers and retry configuration.

## Checklist

Inspect per-queue, NIC and kernel counters and correlate with client symptoms.
See the [Linux interface statistics documentation](https://docs.kernel.org/networking/statistics.html).
