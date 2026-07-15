# Buffer Usage Count Distribution

## What this item shows
- Buffer counts at each clock-sweep usage count from 0 through 5.
- How strongly cached pages have recently been reused.

## What to watch
- Growth in usage counts 0 and 1 alongside physical reads.
- Material shifts in the distribution during workload changes.

## Common fault causes
- One-pass scans or a working set larger than shared buffers.
- A newly warmed or recently restarted server.

## Automatic evaluation
- No severity is assigned; this is not a hit ratio.

## Checklist
- Interpret the distribution over time and alongside physical reads.
- Use relation charts to identify which objects occupy the cache.
