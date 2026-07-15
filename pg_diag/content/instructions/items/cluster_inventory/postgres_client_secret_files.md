# PostgreSQL Client Secret Files

This item reports local PostgreSQL client password and service files with secret or permission findings.

## What this item shows
- Visible `.pgpass` and PostgreSQL service files.
- Service files containing `password` entries.
- Files with permissions broader than owner-only.

## Automatic evaluation
- Severity depends on cleartext credential presence and whether group/other users can read or modify the file.
- Only local candidate files visible to the collector are checked; absence is not a host-wide secret scan.
- Secret values are never included in report evidence.

## Checklist
- Avoid storing cleartext passwords in service files.
- Keep `.pgpass` and service files owner-only.
- Prefer short-lived credentials or external secret management where possible.
