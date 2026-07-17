# Generic Devices

This instruction belongs to report item `os.lshw_generic`. The item is backed by `os.lshw_generic` (local host script).

## What this item shows
- Miscellaneous hardware devices not classified elsewhere by lshw.
- Catch-all inventory for unusual devices.

## What to watch
- Unexpected unknown devices.
- Devices with missing drivers.
- New generic entries after hardware changes.

## Common fault causes
- Driver mismatch.
- Firmware change.
- VM hardware profile change.

## Automatic evaluation
- No severity is assigned; generic devices require platform-specific identification.
- Empty output is valid and unknown devices are not automatically security or performance findings.

## Related report items
- [os.lshw_system](#item-os.lshw_system) — Review generic devices in the full hardware inventory.

## Checklist
- Review only entries related to database storage, network, or security policy.
- Compare before/after hardware maintenance.
- Escalate unknown production devices when policy requires.
