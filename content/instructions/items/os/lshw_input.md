# Input Devices

This instruction belongs to report item `os.lshw_input`. The item is backed by `os.lshw_input` (local host script).

## What this item shows
- Input device inventory visible to lshw.
- Incidental hardware inventory on the database host.

## What to watch
- Unexpected physical input devices on a server.
- Inventory noise from virtual devices.

## Common fault causes
- Hypervisor exposing generic input devices.
- Non-standard host image.

## Automatic evaluation
- No severity is assigned; input devices are inventory-only evidence.
- Empty output is normal on headless servers and many VMs.

## Checklist
- Treat as inventory context only.
- Ignore normal virtual input devices unless security policy requires review.
- Do not use this item for database performance diagnosis.
