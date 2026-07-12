# Top Dirty Relations In Buffer Cache

## What this item shows
- The 30 current-database relations with the most dirty blocks plus `Other`.
- Dirty-cache composition with independent membership per snapshot.

## What to watch
- Sustained dirty residency concentrated in a few relations.

## Common fault causes
- Heavy DML, delayed writeback, or checkpoint activity.

## Automatic evaluation
- No severity is assigned; dirty occupancy alone does not prove a bottleneck.

## Checklist
- Correlate with DML, checkpoints, writeback, and storage latency.
- Treat `Other` as the bounded remainder.
