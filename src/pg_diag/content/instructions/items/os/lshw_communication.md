# Communication Devices

This instruction belongs to report item `os.lshw_communication`. The item is backed by `os.lshw_communication` (local host script).

## What this item shows
- Communication device inventory such as serial, modem, or management interfaces.
- Non-network communication hardware visible to lshw.

## What to watch
- Unexpected communication devices on a database host.
- Management interfaces that violate platform policy.

## Common fault causes
- Generic hardware image.
- Out-of-band device exposure.
- VM virtual device defaults.

## Automatic evaluation
- No severity is assigned because communication-device policy is deployment-specific.
- Empty class output is normal; unexpected devices require comparison with the platform baseline.

## Related report items
- [os.network_addresses](#item-os.network_addresses) — Check whether communication devices carry database traffic.
- [os.lshw_network](#item-os.lshw_network) — Compare communication and network hardware inventories.

## Checklist
- Review only for inventory or security policy questions.
- Confirm unexpected devices with platform owners.
- Do not infer database workload behavior from this item.
