# Installed Risky Extensions

This instruction belongs to report item `cluster_inventory.installed_risky_extensions`.

This item reports installed extensions and untrusted procedural languages with elevated security impact.

## What this item shows
- Extensions such as `dblink`, `file_fdw`, `adminpack`, or untrusted procedural languages.
- Extension schema and version where available.
- Risk reason for each installed object.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- `medium`: server-file/admin helpers or untrusted languages expand privileged-code impact.
- `unknown`: dblink/FDW installation requires grants, mappings, and stored-credential review.
- Installation alone is not proof that untrusted users can execute the capability.

## Related report items
- [cluster_inventory.extensions](#item-cluster_inventory.extensions) — Review the full installed and available extension inventory.
- [os.extension_directory_permissions](#item-os.extension_directory_permissions) — Verify extension binary protection.
- [object_workload.extension_objects_acl_drift](#item-object_workload.extension_objects_acl_drift) — Check access-control changes on extension objects.

## Checklist
- Keep high-impact extensions installed only where there is a clear operational need.
- Restrict EXECUTE and CREATE privileges around risky extension functions.
- Remove unused untrusted procedural languages and server-file access extensions.
