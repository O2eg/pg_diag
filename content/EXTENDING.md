# Extending The Report

## Add A Table

For an existing section, a DBA usually changes only two places:

1. Add SQL:

   `queries/<group>/<new_query>.sql`

2. Add a query manifest to the matching `catalog/<group>.yaml`:

   ```yaml
   queries:
     locks.wait_summary:
       title: Lock Wait Summary
       group: Activity & Locks
       main_view: pg_locks
       description: Aggregated lock waits by lock type and mode.
       source: custom
       display:
         default_sort:
           column: wait_ms
           direction: desc
       collection:
         default: once
         supports: [once, every_snapshot]
       variants:
         - id: locks_wait_summary_all
           min_pg_version: 120000
           sql_file: locks/wait_summary.sql
   ```

3. Add a lightweight report item to `report.yaml`:

   ```yaml
   activity_locks:
     items:
       wait_summary:
         query: locks.wait_summary
   ```

The item title, description, source metadata, and table shape are inherited from the query catalog unless explicitly overridden in `report.yaml`.

## Add A Chart

A chart uses a query that can be collected repeatedly. The physical column names stay in the query manifest as semantic mappings; the metric references semantic names.

1. Ensure the source query supports repeated collection:

   ```yaml
   collection:
     default: once
     supports: [once, every_snapshot]
   variants:
     - id: custom_query_pg16_plus
       min_pg_version: 160000
       sql_file: custom/query.sql
       semantic_columns:
         dimensions:
           database: datname
         counters:
           bytes_written: bytes_written
   ```

2. Add a metric to `metrics.yaml`:

   ```yaml
   custom.bytes_written_rate:
     title: Bytes Written Rate
     source_query: custom.query
     requires_collection: every_snapshot
     partition_by:
       - dimensions.database
     series:
       - name: bytes written
         value_ref: counters.bytes_written
         transform: rate
         unit: bytes/s
     chart:
       kind: line
       unit: bytes/s
   ```

3. Add a lightweight chart item to `report.yaml`:

   ```yaml
   charts:
     items:
       bytes_written_rate:
         metric: custom.bytes_written_rate
   ```

The planner should promote the source query to `every_snapshot` for this metric without changing table items that use the same query.
