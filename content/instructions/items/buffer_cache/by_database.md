# Buffer Cache By Database

## What this item shows
- Cached blocks attributed to every cluster database and shared catalogs.
- Cluster-wide shared-buffer composition by database.

## What to watch
- A database rapidly displacing the established cache composition.

## Common fault causes
- Bulk scans, maintenance, or a workload shift in one database.

## Automatic evaluation
- No severity is assigned. Occupancy is not workload rate.

## Checklist
- Use Buffer Cache Utilization for unused buffers, which are excluded here.
- Correlate changes with per-database workload and I/O charts.
