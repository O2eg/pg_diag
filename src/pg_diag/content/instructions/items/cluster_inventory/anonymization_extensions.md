# Anonymization Extensions

This instruction belongs to report item `cluster_inventory.anonymization_extensions`.

This item reports missing anonymization extension installation or preload configuration.

## What this item shows
- Availability of `anon` and `pg_anonymize`.
- Installed version in the connected database.
- Current `session_preload_libraries` value.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- Severity is `unknown`: an anonymization extension is one possible control, not a universal requirement.
- Preload matching uses exact comma-separated library names rather than substring matching.

## Related report items
- [cluster_inventory.extensions](#item-cluster_inventory.extensions) — Review installation and availability details.
- [object_workload.rls_configuration](#item-object_workload.rls_configuration) — Compare anonymization controls with row-level access policy.
- [cluster_inventory.installed_risky_extensions](#item-cluster_inventory.installed_risky_extensions) — Review elevated extension capabilities.

## Checklist
- Install and configure an anonymization extension where sensitive data masking is required.
- Add the extension to `session_preload_libraries` if the chosen tool requires session preload.
- Review anonymization rules as part of data access and export workflows.
