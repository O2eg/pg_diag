# Kernel And Architecture

This instruction belongs to report item `os.kernel_version`. The item is backed by `os.kernel_version` (local host script).

## What this item shows
- Kernel release, architecture, and local build identifier.
- Whether the collector host is the expected Linux host for local collection.

## What to watch
- Kernel much older than the supported platform baseline.
- Architecture mismatch with expected packages or extensions.
- Kernel version changed without a corresponding reboot plan.

## Common fault causes
- Host booted into an older kernel after patching.
- Collector running in a container or namespace that hides the real host.
- Unsupported kernel/distribution combination.

## Automatic evaluation
- No severity is assigned because support, vulnerability, and reboot status require external vendor/package data.
- The value comes from the collector's current UTS namespace; containers can expose a host kernel unrelated to the container image.

## Checklist
- Confirm kernel support with the OS vendor baseline.
- Check whether kernel security updates require reboot.
- Compare with `OS Distribution` and package maintenance records.
