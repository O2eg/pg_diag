# Installed Risky Extensions

This item reports installed extensions and untrusted procedural languages with elevated security impact.

## What this item shows
- Extensions such as `dblink`, `file_fdw`, `adminpack`, or untrusted procedural languages.
- Extension schema and version where available.
- Risk reason for each installed object.

## Automatic evaluation
- `medium`: server-file/admin helpers or untrusted languages expand privileged-code impact.
- `unknown`: dblink/FDW installation requires grants, mappings, and stored-credential review.
- Installation alone is not proof that untrusted users can execute the capability.

## Checklist
- Keep high-impact extensions installed only where there is a clear operational need.
- Restrict EXECUTE and CREATE privileges around risky extension functions.
- Remove unused untrusted procedural languages and server-file access extensions.
