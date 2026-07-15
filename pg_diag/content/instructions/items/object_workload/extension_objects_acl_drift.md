# Extension Objects ACL Drift

This item lists extension-owned objects that have explicit ACL entries.

## What this item shows
- Extension name.
- Object kind, schema, object name, and ACL text.

## Automatic evaluation
- Severity is `unknown`: an explicit ACL is not evidence of harmful drift without an extension baseline.
- Results are bounded to 1000 objects; verify upgrade behavior before changing extension-owned ACLs.

## Checklist
- Confirm the ACL is intentional and survives extension upgrades.
- Avoid editing extension object grants unless required.
- Re-test extension upgrade paths after grant changes.
