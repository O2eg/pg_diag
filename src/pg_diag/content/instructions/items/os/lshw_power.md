# Power Components

This instruction belongs to report item `os.lshw_power`. The item is backed by `os.lshw_power` (local host script).

## What this item shows
- Power supply or battery inventory visible to lshw.
- Hardware power component context.

## What to watch
- Battery or power device state unexpected for server hardware.
- Missing power inventory on bare metal.

## Common fault causes
- Hardware monitoring limitation.
- VM hides real power devices.
- Power component replacement.

## Automatic evaluation
- No severity is assigned because lshw does not provide authoritative health telemetry.
- Empty output is expected in VMs; use BMC/cloud monitoring for actual power health.

## Related report items
- [os.lshw_system](#item-os.lshw_system) — Place power components in the overall system inventory.

## Checklist
- Use platform monitoring for real power health.
- Treat virtual power devices as inventory noise.
- Escalate bare-metal power anomalies to operations.
