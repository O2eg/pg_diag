# Object ACL Drift

This item finds same-kind objects in one schema with inconsistent ACL signatures.

## What this item shows
- Schema and object kind.
- Number of distinct ACL signatures.
- Sample object names from the affected group.

## Automatic evaluation
- Severity is `unknown`: unlike ACL signatures can be legitimate for different object purposes.
- The check identifies drift candidates but cannot infer the application privilege baseline.

## Checklist
- Compare grants for objects in the same application area.
- Reapply expected grants with migration tooling.
- Prefer default privileges for future objects.
