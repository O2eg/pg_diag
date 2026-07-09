# Object ACL Drift

This item finds same-kind objects in one schema with inconsistent ACL signatures.

## What this item shows
- Schema and object kind.
- Number of distinct ACL signatures.
- Sample object names from the affected group.

## Checklist
- Compare grants for objects in the same application area.
- Reapply expected grants with migration tooling.
- Prefer default privileges for future objects.
