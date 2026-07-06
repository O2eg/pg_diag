# pg_wait_sampling Capability Check

This instruction belongs to report item `activity_locks.pg_wait_sampling_capabilities`. The item is backed by `wait.pg_wait_sampling_capabilities` (SQL query).

## What this item shows
- Whether pg_wait_sampling is available, installed, and exposes the profile view.
- Why pg_wait_sampling profile data may be unavailable.
- Extension readiness for historical wait sampling.

## What to watch
- Extension package not available.
- Extension not installed in current database.
- Profile view missing.

## Common fault causes
- Package not installed on host.
- CREATE EXTENSION not run.
- Extension not allowed in managed service.

## Checklist
- Install only if operational policy allows it.
- Use pg_stat_activity wait samples when pg_wait_sampling is unavailable.
- Confirm extension overhead and retention expectations.
