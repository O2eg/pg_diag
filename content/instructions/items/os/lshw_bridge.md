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

## Checklist
- Review after storage/network device changes.
- Use with device-specific lshw sections.
- Escalate topology surprises to platform owners.
