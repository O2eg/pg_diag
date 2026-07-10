# Network Interfaces

This instruction belongs to report item `os.lshw_network`. The item is backed by `os.lshw_network` (local host script).

## What this item shows
- Network interface hardware inventory, driver, bus, and link details where visible.
- Device-level context for client and replication network paths.

## What to watch
- Wrong NIC model, speed, driver, or missing interface.
- Interface not matching expected production network.
- Virtual NIC changes after migration.

## Common fault causes
- VM network adapter change.
- Driver/firmware mismatch.
- Host moved to different network class.

## Automatic evaluation
- No severity is assigned without expected NIC, driver, speed, and bonding policy.
- Missing link details can result from permissions or virtualization; correlate with runtime addresses and network monitoring.

## Checklist
- Compare with `Network Addresses And Hosts`
- Check NIC speed and driver when network throughput or replication lag is suspected.
- Confirm active interface is the intended one.
