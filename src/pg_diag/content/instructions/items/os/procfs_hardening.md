# procfs Hardening

This instruction belongs to report item `os.procfs_hardening`.
It is backed by local Python source `security.procfs_hardening`.

## What this item shows
- `kernel.yama.ptrace_scope`.
- `/proc` mount options such as `hidepid`.

## What to watch
- `ptrace_scope=0` or `/proc` without `hidepid=1/2` on a multi-user host.

## Automatic evaluation
- Each missing hardening control is `medium`, not proof of exploitability.
- If neither sysctl nor mount evidence can be read, the item is `unsupported`. Containers may expose namespace-specific mount options.

## Common fault causes
- Distribution defaults, monitoring compatibility requirements, container procfs mounts, or hardening changes not persisted.

## Related report items
- [backend_os.backend_proc_cpu](#item-backend_os.backend_proc_cpu) — Understand whether procfs restrictions affect backend CPU collection.
- [backend_os.backend_proc_io](#item-backend_os.backend_proc_io) — Understand whether procfs restrictions affect backend I/O collection.
- [os.postgres_service_hardening](#item-os.postgres_service_hardening) — Compare kernel and service isolation controls.

## Checklist
- Use `ptrace_scope` to limit same-user process inspection.
- Mount `/proc` with `hidepid=1` or `hidepid=2` where compatible.
- Verify monitoring tools still work after hardening.
