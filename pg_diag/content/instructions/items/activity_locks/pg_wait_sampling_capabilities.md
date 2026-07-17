# pg_wait_sampling Capability Check

This instruction belongs to report item `activity_locks.pg_wait_sampling_capabilities`. The item is backed by `wait.pg_wait_sampling_capabilities` (SQL query).

## What this item shows
- Whether the optional `pg_wait_sampling` package is available and installed in the connected database.
- The extension schema and whether `pg_wait_sampling_profile` is visible on pg_diag's `pg_catalog, public` search path.
- Why the profile item may be unsupported.

## What to watch
- Installed extension in a schema not visible on the configured search path.
- Installed extension with a missing profile view.
- Managed-service or package policy that intentionally makes the extension unavailable.

## Automatic evaluation
- No severity is assigned: `pg_wait_sampling` is optional and its absence is not a database fault.
- Capability `false` is evidence of unavailability, while a collection error means the capability check itself failed.

## Common fault causes
- Host package not installed, `CREATE EXTENSION` not run, or extension disallowed by the provider.
- Extension installed outside `public` while pg_diag uses a restricted search path.

## Related report items
- [activity_locks.pg_wait_sampling_profile](#item-activity_locks.pg_wait_sampling_profile) — Open the extension profile when the capability check succeeds.
- [activity_locks.wait_event_sample_profile](#item-activity_locks.wait_event_sample_profile) — Use built-in activity sampling when the extension is unavailable.

## Checklist
- Use the built-in snapshot wait chart when the extension is unavailable.
- Install or relocate the extension only under the site's change and security policy.
- Confirm sampling interval, overhead, profile query-ID configuration, and reset policy before operational use.
