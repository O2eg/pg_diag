# Extension Objects ACL Drift

This item lists extension-owned objects that have explicit ACL entries.

## What this item shows
- Extension name.
- Object kind, schema, object name, and ACL text.

## Checklist
- Confirm the ACL is intentional and survives extension upgrades.
- Avoid editing extension object grants unless required.
- Re-test extension upgrade paths after grant changes.
