# Kernel TCP Parameters

This instruction belongs to report item `os.sysctl_tcp`. The item is backed by `os.sysctl_tcp` (local host script).

## What this item shows
- Kernel IPv4 TCP settings relevant to connection handling and network behavior.
- Runtime values for backlog, keepalive, retransmission, and buffer behavior.

## What to watch
- Keepalive values inconsistent with load balancer or firewall timeouts.
- Backlog or buffer limits too small for connection bursts.
- Values that differ across primary and standby hosts.

## Common fault causes
- Default kernel networking settings.
- Connection pool bursts.
- Firewall idle timeouts.
- Configuration drift.

## Automatic evaluation
- No severity is assigned without proxy, firewall, kernel, and connection-rate context.
- Only readable runtime `net.ipv4.tcp*` keys are shown; IPv6 and persistence are outside this item.

## Checklist
- Compare TCP settings with application pool and proxy behavior.
- Check connection pressure before changing network queues.
- Persist approved network sysctl changes.
