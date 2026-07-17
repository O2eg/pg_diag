# PostgreSQL Client Secret Files

This instruction belongs to report item `cluster_inventory.postgres_client_secret_files`.

This item reports local PostgreSQL client password and service files with secret or permission findings.

## What this item shows
- Visible `.pgpass` and PostgreSQL service files.
- Service files containing `password` entries.
- Files with permissions broader than owner-only.

## What to watch
- Findings whose severity or evidence differs from the approved cluster security baseline.
- Broad access, weak authentication, sensitive-file exposure, or missing controls that compound other findings.

## Common fault causes
- Package or cloud defaults, legacy compatibility, incomplete hardening, or undocumented operational exceptions.
- A change in one security layer without corresponding role, HBA, filesystem, or extension controls.

## Automatic evaluation

- Severity depends on cleartext credential presence and whether group/other users can read or modify the file.
- Only local candidate files visible to the collector are checked; absence is not a host-wide secret scan.
- Secret values are never included in report evidence.

## Related report items
- [os.postgres_env_secret_leaks](#item-os.postgres_env_secret_leaks) — Check credentials exposed through process environments.
- [os.postgres_history_files](#item-os.postgres_history_files) — Check secrets retained in history files.
- [cluster_inventory.role_password_hashes](#item-cluster_inventory.role_password_hashes) — Review server-side password verifiers.

## Checklist
- Avoid storing cleartext passwords in service files.
- Keep `.pgpass` and service files owner-only.
- Prefer short-lived credentials or external secret management where possible.
