# Relation Cache Residency Delta

## What this item shows
- Signed cached-block changes between adjacent snapshots.
- Positive net residency gained and negative net residency lost.

## What to watch
- Repeated losses from important relations or large gains from bulk-accessed objects.

## Common fault causes
- Working-set competition, bulk scans, maintenance, or cache warming.

## Automatic evaluation
- No severity is assigned. This is a gauge difference, not an eviction counter.

## Checklist
- Do not interpret net change as exact loads or evictions.
- Treat an absent endpoint as unknown, never zero.
