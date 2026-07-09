# procfs Hardening

This item checks process-inspection hardening settings.

## What this item shows
- `kernel.yama.ptrace_scope`.
- `/proc` mount options such as `hidepid`.

## Checklist
- Use `ptrace_scope` to limit same-user process inspection.
- Mount `/proc` with `hidepid=1` or `hidepid=2` where compatible.
- Verify monitoring tools still work after hardening.
