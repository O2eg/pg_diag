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

## Checklist
- Review only entries related to database storage, network, or security policy.
- Compare before/after hardware maintenance.
- Escalate unknown production devices when policy requires.
