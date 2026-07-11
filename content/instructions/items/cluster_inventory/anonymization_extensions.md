# Anonymization Extensions

This item reports missing anonymization extension installation or preload configuration.

## What this item shows
- Availability of `anon` and `pg_anonymize`.
- Installed version in the connected database.
- Current `session_preload_libraries` value.

## Automatic evaluation
- Severity is `unknown`: an anonymization extension is one possible control, not a universal requirement.
- Preload matching uses exact comma-separated library names rather than substring matching.

## Checklist
- Install and configure an anonymization extension where sensitive data masking is required.
- Add the extension to `session_preload_libraries` if the chosen tool requires session preload.
- Review anonymization rules as part of data access and export workflows.
