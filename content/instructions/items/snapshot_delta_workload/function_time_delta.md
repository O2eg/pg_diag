# Function Time Delta

This instruction belongs to report item `snapshot_delta_workload.function_time_delta`. The item is backed by `objects.function_time_delta` (snapshot metric).

## What this item shows
- Per-function call and time deltas during the capture window.
- Procedural code consuming time during snapshots mode.

## What to watch
- High function time per second.
- High call rate for a PL function.
- Missing data because track_functions is disabled.

## Common fault causes
- Expensive PL/pgSQL loops.
- Function hides SQL work.
- Application calls function too frequently.

## Checklist
- Confirm `track_functions` setting.
- Profile high-time functions.
- Review function body and called SQL.
