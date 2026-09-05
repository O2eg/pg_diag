# Network Interface Errors

This instruction belongs to report item `snapshot_charts_os.os_network_errors`. The item is backed by `os.network_errors` (snapshot metric).

## What this item shows

Receive and transmit error rates per non-loopback interface, calculated from
successive `/proc/net/dev` counters. Units are packets/second, not lifetime totals.
Counter rollback and missing endpoints remain unknown, not zero.

## What to watch

- New errors in either direction, spikes and repeated errors on one interface.

## Common fault causes

Errors can indicate a link, driver, device or transmission problem. Correlate
them with interface inventory, traffic and drops; do not add drops to errors as
independent lost packets. Aggregate host counters do not identify PostgreSQL traffic.

## Automatic evaluation

In the diagnostic graph any observed error raises a warning; a peak of 10 errors
per second raises a critical triage flag. These are graph heuristics, not a link SLA.

## Related report items

- [snapshot_charts_os.os_network_drops](#item-snapshot_charts_os.os_network_drops) — Compare drop rates without double-counting losses.
- [snapshot_charts_os.os_network_packets](#item-snapshot_charts_os.os_network_packets) — Check packet volume on the same interface.
- [os.lshw_network](#item-os.lshw_network) — Identify the NIC and driver.

## Checklist

Check driver-specific `ethtool -S` and `ip -s -s link` counters before attributing
an application timeout to hardware. See the
[Linux interface statistics documentation](https://docs.kernel.org/networking/statistics.html).
