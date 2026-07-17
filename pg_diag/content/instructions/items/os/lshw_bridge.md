# Bridges And Controllers

This instruction belongs to report item `os.lshw_bridge`. The item is backed by `os.lshw_bridge` (local host script).

## What this item shows
- Bridge and controller hardware inventory.
- Chipset or virtual controller context for attached devices.

## What to watch
- Unexpected bridge/controller changes.
- Missing controller inventory.
- Hardware topology inconsistent with expected platform.

## Common fault causes
- Host replacement.
- VM hardware version change.
- Driver or permission issue.

## Automatic evaluation
- No severity is assigned; bridge/controller presence is platform-specific.
- Empty class output can be normal for a VM; lshw stderr warnings mark incomplete evidence.

## Related report items
- [os.lshw_bus](#item-os.lshw_bus) — Place bridge devices in the bus hierarchy.
- [os.lshw_storage](#item-os.lshw_storage) — Check storage controllers attached through bridges.

## Checklist
- Review after storage/network device changes.
- Use with device-specific lshw sections.
- Escalate topology surprises to platform owners.
