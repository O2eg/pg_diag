# Report Item And Chart Data Specification

Status: normative schema-version-4 contract for new PostgreSQL,
operating-system, Python, Bash, metric-table, and chart content. It is also the
migration target for legacy declarations explicitly listed in Section 19.

The schema-version-4 descriptor and artifact pipeline is active. New content
must comply with this document. A successful `pg-diag validate` proves the
currently implemented structural checks; it does not waive the remaining
semantic migration requirements identified in Section 19.

## 1. Goals

This specification separates collection, meaning, transport, and presentation:

1. A source returns exact raw values in canonical base units.
2. Declarative metadata describes the logical type, semantic role, quantity,
   unit, quality, nullability, and JSON encoding of every displayed field.
3. The artifact preserves those values without presentation rounding or loss of
   integer precision.
4. One shared unit registry formats table cells, summaries, chart axes, chart
   tooltips, labels, and exact-value details.
5. Filtering, sorting, evaluation, and aggregation use raw typed values, never
   formatted text.

The renderer must not infer a unit from a column name. Content-owned
presentation rules may construct a descriptor from physical type and stable
source context before rendering. Adaptive SI scaling is valid only for fields
whose resolved descriptor declares `unit: count` or `unit: blocks`; it must not
be applied generically to arbitrary numeric fields.

## 2. Normative Language

`MUST`, `MUST NOT`, `SHOULD`, and `MAY` are normative terms.

- `raw value` is the collected or derived value before display formatting.
- `display value` is renderer-owned text and is never written back to JSON.
- `exact integer` is an integer whose value must survive collection, Delta
  calculation, JSON serialization, and browser sorting without precision loss.
- `canonical unit` is the unit stored in the artifact and used by evaluations.
- `adaptive unit` is a renderer-selected IEC prefix used only for display.

## 3. Field Type Model

Physical PostgreSQL types such as `int8` and `numeric` are not sufficient to
describe a report field. Every displayed field MUST have the following logical
descriptor.

```yaml
name: temp_io_bytes_delta
label: Temp I/O
value_kind: integer
semantic_role: counter_delta
quantity: data_volume
unit: bytes
quality: exact
nullable: false
encoding: decimal_string
```

### 3.1 `value_kind`

Allowed initial values:

| Value | Meaning |
|---|---|
| `integer` | Integral numeric value |
| `decimal` | Finite decimal/rate/ratio value |
| `text` | Ordinary text |
| `boolean` | Boolean value |
| `timestamp` | An instant in time |
| `date` | Calendar date without time |
| `time` | Time of day; timezone semantics must be declared by the source |
| `lsn` | PostgreSQL LSN in canonical `X/Y` form |
| `json` | Structured JSON value rendered as structured text, not a number |

`identifier`, `timestamp`, and `boolean` are logical kinds or roles; they are
not measurement units.

### 3.2 `semantic_role`

Allowed initial values:

| Value | Meaning |
|---|---|
| `identifier` | Identity or join key; never scaled |
| `counter` | Monotonic cumulative counter |
| `counter_delta` | Difference between comparable counter endpoints |
| `gauge` | Point-in-time numeric measurement |
| `rate` | Change per unit of time |
| `duration` | Elapsed or accumulated time |
| `estimate` | Approximate value reported as a number |
| `state` | Boolean or textual state |
| `label` | Human-readable dimension |

Only `counter` values may use the `delta` and `rate` transforms. A source gauge
must not be treated as a cumulative counter merely because its physical type is
numeric.

### 3.3 `quantity`

`quantity` describes what is measured and does not control numeric scaling.
Examples include:

```text
data_volume, rows, tuples, calls, transactions, scans, blocks,
sessions, backends, locks, files, WAL_segments, packets, operations,
milliseconds, load_average, percentage, identifier
```

New quantities MAY be added centrally. An item must not redefine how an
existing quantity is formatted.

### 3.4 `unit`

`unit` describes the canonical raw unit. Initial registry values are defined in
Section 7. A field with no physical unit uses `none`.

### 3.5 `quality`

Allowed values:

- `exact`: exact collected or exact derived value;
- `estimated`: source-provided estimate such as `n_live_tup`;
- `sampled`: value inferred from periodic sampling;
- `derived`: deterministic arithmetic result whose inputs may have another
  quality.

Estimated values MUST be labelled as estimates in the header or cell detail.
Automatic severity rules MUST explicitly opt in before evaluating an estimated
value.

### 3.6 `nullable`

`nullable: true` means that `null` is a valid raw value. It does not mean zero,
an empty string, or an unsupported source.

### 3.7 `encoding`

Allowed values:

- `json_number`: finite JSON number;
- `decimal_string`: base-10 numeric string interpreted according to
  `value_kind`;
- `json_string`: ordinary JSON string;
- `json_boolean`: JSON boolean;
- `json_value`: structured JSON value.

The descriptor, not JavaScript `typeof`, determines comparison and formatting.

## 4. Lossless Numeric Transport

JSON consumers commonly use IEEE-754 binary64 numbers and cannot preserve every
integer outside `[-9007199254740991, 9007199254740991]` exactly. Therefore:

- exact integers known to fit the safe range MAY use `json_number`;
- PostgreSQL `int8`, unbounded cumulative counters, absolute LSN byte positions,
  exact byte sizes, and other potentially unsafe integers MUST use
  `decimal_string` consistently for the entire column;
- a column MUST NOT switch between JSON number and string based on the current
  row value;
- `decimal_string` integer values MUST match `^-?(0|[1-9][0-9]*)$`;
- the renderer MUST compare `decimal_string` integers with `BigInt` or an
  equivalent arbitrary-precision integer comparator;
- the metric engine MUST preserve integer arithmetic for integer counter
  Deltas;
- a rate MAY use a finite binary64 `json_number`; presentation rounding happens
  only in the renderer;
- `NaN`, positive infinity, and negative infinity are forbidden in artifacts.

Evaluation thresholds use the same typed comparator. They MUST NOT coerce an
exact integer through `float` or JavaScript `Number`.

## 5. Three-Layer Contract

### 5.1 Source layer

SQL, Bash, and Python sources return canonical raw values. They MUST NOT append
units or produce humanized values such as `6.415 B`, `508.756 M`, `12 GB`, or
`30K`.

Source requirements:

- byte counters and sizes use exact integral bytes;
- block, event, row, tuple, call, transaction, scan, and object counts use
  integral counts;
- PostgreSQL timing fields retain the unit documented by PostgreSQL;
- endpoint SQL returns counters, not precomputed rates;
- timestamps use native temporal values where available;
- SQL does not apply presentation rounding to numeric values or convert bytes
  to kB, MB, or GB;
- unavailable numeric values are `NULL`, never zero or explanatory text;
- identifiers that can exceed the safe JSON integer range, including
  `query_id`, are returned as text or use a declared lossless encoding;
- non-finite numeric values are rejected before artifact creation.

Example:

```sql
select
  statement_timestamp() as snapshot_time,
  temp_blks_written::int8 as temp_blks_written,
  (temp_blks_written::numeric * current_setting('block_size')::int8)
    as temp_bytes
from pg_stat_statements;
```

The source must not return a preformatted `temp_size` string or a fractional
number described as bytes.

### 5.2 Declarative metadata layer

Metadata can be declared at these canonical source paths:

- metric tables: `metrics/<metric_id>/table/columns[]`;
- chart series: `metrics/<metric_id>/series[]` and `top_n` output descriptors;
- query metric inputs:
  `queries/<query_id>/variants[]/semantic_fields/<namespace>/<field>`;
- direct SQL: `queries/<query_id>/display/columns/<column_name>`;
- Bash: `scripts/<script_id>/display/columns/<column_name>`;
- Python: `python_sources/<python_id>/display/columns/<column_name>`;
- sampler output: the provider output schema for each declared output id.

The content-owned `presentation.yaml` catalog MAY provide deterministic type
defaults, context-aware matching rules, and source-specific overrides. These
rules are a loader-stage metadata constructor, not renderer inference. Their
precedence is, from lowest to highest: physical-type default, ordered catalog
rules, source-specific override, source declaration, and metric result-column
declaration. Later catalog rules override earlier rules, so broad rules MUST be
followed by the more specific dimensional rule when their match sets overlap.

Every displayed column MUST have `label`, `value_kind`, `semantic_role`,
`quantity`, `unit`, `quality`, `nullable`, and `encoding` after content loading.
Defaults MAY reduce repetition, but the effective artifact and snapshot schema
MUST contain the complete resolved descriptor. A new field whose meaning is
ambiguous from its physical type and stable source context MUST declare a
source-specific override. The renderer MUST use only resolved descriptors and
MUST NOT run field-name, suffix, source-ID, or physical-type heuristics.

Metric input fields MUST also be typed. A physical-name mapping alone is not
enough for lossless arithmetic:

```yaml
semantic_fields:
  counters:
    temp_io_bytes:
      column: temp_io_bytes
      value_kind: integer
      semantic_role: counter
      quantity: data_volume
      unit: bytes
      quality: exact
      nullable: false
      encoding: decimal_string
```

The selected query variant and sampler output schema own these input
descriptors. Metric transforms validate their input roles and derive the output
descriptor; for example, `rate(counter bytes)` produces `rate bytes/s`.

Metric-table example:

```yaml
columns:
  - name: temp_io_bytes_delta
    label: Temp I/O
    value_ref: counters.temp_io_bytes
    transform: delta
    pg_type: int8
    value_kind: integer
    semantic_role: counter_delta
    quantity: data_volume
    unit: bytes
    quality: exact
    nullable: false
    encoding: decimal_string
  - name: temp_io_bytes_per_sec
    label: Temp I/O rate
    value_ref: counters.temp_io_bytes
    transform: rate
    pg_type: float8
    value_kind: decimal
    semantic_role: rate
    quantity: data_volume
    unit: bytes/s
    quality: derived
    nullable: false
    encoding: json_number
```

Direct-query example:

```yaml
display:
  columns:
    database_size_bytes:
      label: Database size
      value_kind: integer
      semantic_role: gauge
      quantity: data_volume
      unit: bytes
      quality: exact
      nullable: true
      encoding: decimal_string
```

#### Metadata precedence

- A metric result column is owned by its metric column descriptor.
- A direct source result column is owned by its source `display.columns`
  descriptor.
- Cursor metadata such as `pg_type` and `pg_type_oid` supplements but never
  overrides the logical descriptor.
- `report.yaml` controls layout and MUST NOT override column semantics.
- An item-level presentation override MAY change visibility only; it MUST NOT
  change type, quantity, unit, encoding, or quality.

#### Row-dependent units

A column containing values with different units across rows, such as normalized
PostgreSQL settings, MUST use `unit_ref` instead of `unit`:

```yaml
setting_normalized:
  label: Normalized value
  value_kind: decimal
  semantic_role: gauge
  quantity_ref: quantity_normalized
  unit_ref: unit_normalized
  quality: exact
  nullable: true
  encoding: json_number
```

`unit` and `unit_ref` are mutually exclusive. Referenced unit codes MUST belong
to the global registry. The unit-ref column may be hidden from normal table
display but remains in the schema used for validation and rendering.

#### Dynamic table outputs

A Bash, Python, or JSON table with runtime-discovered columns MUST either:

1. declare the complete possible schema in its source manifest; or
2. emit column descriptors conforming to this specification as part of its
   structured result.

An untyped dynamic numeric column is invalid. Truly arbitrary data must use a
`json` or `plain_text` result instead of an inferred numeric table.

### 5.3 Artifact layer

Every public table column in `result.columns` MUST contain the resolved logical
descriptor in addition to its stable `name` and optional physical type:

```json
{
  "name": "temp_io_bytes_delta",
  "label": "Temp I/O",
  "value_kind": "integer",
  "semantic_role": "counter_delta",
  "quantity": "data_volume",
  "unit": "bytes",
  "quality": "exact",
  "nullable": false,
  "encoding": "decimal_string",
  "pg_type": "int8"
}
```

Snapshot schemas carry the same descriptors. Compact snapshot rows reference
that schema and MUST use the declared encoding.

Complete descriptors are part of content and artifact schema version 4. A future
incompatible descriptor change requires another content and artifact schema
version increase. The current runtime accepts its current artifact schema and
rejects other versions with an explicit unsupported-version error; it must not
silently fall back to suffix inference.

### 5.4 Presentation layer

The renderer receives the raw value and resolved descriptor and produces display
text without modifying the artifact.

One formatter registry is used by:

- table cells and summaries;
- chart axes, tooltips, and data labels;
- finding summaries containing measured values;
- report time and duration labels.

## 6. Cell And Column Status

An item may succeed while one cell or one version-specific column is unavailable.
Numeric columns must remain type-stable in those cases.

### 6.1 Cell status

The raw cell value is `null`. A sparse `result.cell_statuses` array carries the
presentation reason:

```json
{
  "row_index": 1,
  "column": "database_size_bytes",
  "status": "timeout",
  "reason": "Database size calculation exceeded 10 seconds"
}
```

Allowed initial statuses are `timeout`, `error`, `permission_denied`,
`unavailable`, and `unsupported`.

`row_index` identifies the immutable row position in artifact order. The
renderer must retain that original index while filtering, sorting, and paging;
it must not reinterpret the index as the current visual row number.

The renderer displays a concise status such as `Timeout` in that cell and keeps
the detailed reason in title/detail text. Sorting treats the raw value as null.
Filtering searches both display status and reason. A partial cell failure does
not convert the item to an error when other requested data was collected; it
adds an item diagnostic.

### 6.2 Column status

A version-specific column unavailable for every row uses
`result.column_statuses`:

```json
{
  "slru_written_delta": {
    "status": "unsupported",
    "reason": "The source counter is not exposed by this PostgreSQL version"
  }
}
```

Its cells are `null`. A fabricated zero placeholder is forbidden.

### 6.3 Null, zero, empty, and unsupported

- `null` means no raw value was observed.
- zero means a successfully observed numeric zero.
- an empty string is a valid text value only when the source contract allows it.
- item `unsupported` means the source feature itself is unavailable.
- cell/column status means the item exists but a value is unavailable.
- explanatory text MUST NOT be written into a numeric cell.

## 7. Canonical Unit Registry

Only the following initial units may be used without centrally extending the
registry.

| Unit | Raw value | Table display |
|---|---|---|
| `none` | type-dependent | No unit suffix |
| `count` | integer | Adaptive SI count such as `37.9 M`; quantity is stated by the label |
| `count/s` | decimal | Grouped decimal plus `/s` when needed for clarity |
| `bytes` | exact integer bytes | Adaptive IEC value such as `485.19 MiB` |
| `bytes/s` | decimal bytes per second | Adaptive IEC value such as `15.91 MiB/s` |
| `blocks` | integer blocks | Adaptive SI count such as `34.603 M`; the column label states blocks |
| `blocks/s` | decimal blocks per second | Decimal plus `blocks/s` |
| `milliseconds` | decimal milliseconds | Adaptive duration such as `842 ms`, `12.5 s`, `6 min 44.961 s`, or `2 h 7 min 3 s` |
| `milliseconds/s` | decimal milliseconds per second | Decimal plus `ms/s` |
| `seconds` | decimal seconds | Decimal plus `s` |
| `percent` | decimal in `[0, 100]` | Decimal plus `%` |
| `ratio` | decimal ratio | Decimal with no suffix |
| `operations/s` | decimal operations per second | Decimal plus `ops/s` |
| `iops` | decimal storage I/O operations per second | Decimal plus `IOPS` |
| `hertz` | decimal cycles per second | Adaptive `Hz`, `kHz`, `MHz`, or `GHz` |
| `bits` | exact integer bits | Grouped integer plus `bits` |
| `bits/s` | decimal bits per second | Adaptive SI value such as `10 Gb/s` |
| `load` | decimal load average | Decimal with no suffix |

Textual `lsn`, timestamp, date, time, boolean, and identifier fields use
`unit: none`; their logical kind controls formatting.

Existing content-specific words such as `sessions`, `backends`, `deadlocks`,
`files`, `packets`, `rows`, `tuples`, `calls`, `transactions`, and `scans` are
quantities paired with `count` or `count/s`, not separate numeric formatters.

## 8. Byte Quantities

All binary byte quantities use IEC binary prefixes:

```text
B, KiB, MiB, GiB, TiB, PiB, EiB
```

The base is 1024. `KB`, `MB`, `GB`, and ambiguous bare compact suffixes `K`,
`M`, and `B` are forbidden for binary byte quantities.

Raw byte counts are exact integers. A display such as `485.19 MiB` is a
converted mebibyte value, not fractional bytes. Exact raw value detail remains
available:

```text
485.19 MiB
exact: 508,755,968 B
```

Rates are decimals because an integer Delta is divided by the actual fractional
interval. `15.91 MiB/s` is valid; bare `16680336.502` is not an acceptable table
display.

### 8.1 Deterministic IEC algorithm

For a finite raw value `v`:

1. Zero displays as `0 B` or `0 B/s`.
2. Select the largest prefix whose factor is not greater than `abs(v)`.
3. Divide by that factor.
4. Round to at most two fractional digits using round-half-away-from-zero.
5. Remove trailing fractional zeroes.
6. If rounding produces `1024` and a larger prefix exists, promote once and
   repeat formatting.
7. Preserve the sign; never display negative zero.

Values below 1024 bytes display as an integer number of bytes. The exact raw
value shown in detail uses digit grouping but no scaling.

## 9. Block And Page Quantities

A block counter is an integral count. Tables use decimal SI magnitude prefixes
for readability, while the exact grouped value remains available in the cell
tooltip. The magnitude suffix is not a byte unit: the column label identifies
the quantity as blocks.

```text
34.603 M
exact: 34,602,771 blocks
```

Byte conversion is source-specific. The following sizes are not interchangeable:

| Block family | Authoritative size |
|---|---|
| relation, shared-buffer, and PostgreSQL temp blocks | `current_setting('block_size')` |
| WAL blocks | `current_setting('wal_block_size')` |
| WAL segments | `current_setting('wal_segment_size')` |
| `pg_stat_io` operations on PG16-PG17 | row `op_bytes` |
| OS device sectors/blocks | source-provided device logical sector/block size |
| SLRU or implementation-specific pages | convert only when the source exposes an authoritative size |

When byte volume is useful, expose a separate exact byte field. Never assume an
8192-byte page and never apply PostgreSQL `block_size` to an OS device counter.

## 10. Counts, Estimates, Percentages, And Ratios

### 10.1 Counts

Table fields with resolved `unit: count` use adaptive decimal SI magnitudes
(`K`, `M`, `G`, and higher registry-supported prefixes) and expose the exact
grouped integer in cell detail. Values below the first scaling boundary display
as grouped integers. IDs, OIDs, PIDs, ports, timelines, LSNs, query IDs, and
system identifiers use the identifier role with `unit: none`; they are never
grouped or scaled.

Chart axes MAY use a single SI count scale (`k`, `M`, `G`) to save space. The
axis title states the scale and chart tooltips show the exact grouped count.

For a sampled gauge, `transform: difference` means the signed arithmetic
difference between adjacent available samples. It permits negative values and
must not be used for cumulative counters. If either endpoint is absent, the
result is `null`; a newly appearing or disappearing dynamic Top-N member is
never interpreted as zero.

The first sample of a `rate`, counter `delta`, or gauge `difference` series is
an endpoint baseline and has a `null` value. The renderer must not display a
leading or trailing timestamp for which every series is `null`; it must retain
all-null timestamps inside the populated range as visible gaps. A baseline is
never converted to zero.

### 10.2 Estimates

An integer physical representation does not imply an exact measurement.
Estimated values use `quality: estimated`, a label such as `Estimated live
tuples`, and detail text identifying the source estimate. They MAY display a
leading `~` but the artifact remains unchanged.

### 10.3 Percentages

Canonical percent values are in `[0, 100]`. A source ratio in `[0, 1]` must use
`unit: ratio` unless a declared derived transform multiplies it by 100. An
undefined denominator produces `null`, not zero.

## 11. Timestamp And Duration Rules

Artifact instants MUST use the RFC 3339 subset of ISO 8601, normalized to UTC:

```text
2026-07-12T16:32:26.597897Z
```

The artifact never stores browser-local timestamps. The renderer converts an
instant to the browser timezone and displays:

```text
2026-07-12 19:32:26.598 GMT+03:00
```

Rules:

- exact UTC text remains available in title/detail text;
- one-shot tables hide system `snapshot_time` and show `One-shot time`;
- repeatedly sampled point-in-time tables hide system `snapshot_time` and show `Snapshot time`;
- Delta tables show `Snapshot start time`, `Snapshot finish`, and
  `Delta duration`;
- ordinary business timestamps remain columns;
- Delta duration uses exact endpoints, not configured duration or snapshot
  count;
- invalid or missing instants display `N/A` and produce a diagnostic;
- every collected non-metric item receives collector-generated `collected_at`;
  a table `snapshot_time` column takes precedence for the displayed table time,
  otherwise the renderer uses `collected_at`;
- metric tables use their source `snapshot_time` or `delta_window` endpoints and
  do not use the ordinary item `collected_at` label;
- `date` and `time` values are not timezone-converted;
- PostgreSQL infinity timestamps must be text/state values or null; they are not
  parsed as finite instants.

## 12. Table Rules

### 12.1 Headers and cells

Every displayed column MUST define a human `label`; raw snake_case is never the
normal header. Machine `name` remains the stable JSON, filter, sort, and
evaluation key.

Measurement cells include an unambiguous unit symbol when the display scale can
vary by row. Count and block cells rely on their quantity-specific column label;
they do not repeat words such as `blocks` in every cell. Examples:

```text
Temp blocks read       30.988 K
Temp I/O               485.19 MiB
Temp I/O rate          15.91 MiB/s
Execution time         2.294 s
Sessions               12
```

### 12.2 Sorting

Interactive and default sorting use raw typed values:

- `decimal_string` integers use an arbitrary-precision integer comparator;
- decimal/rate values use finite numeric comparison;
- timestamps use parsed UTC epoch values;
- text uses `Intl.Collator` or an equivalent comparator configured with the
  report numeric locale, `numeric: true`, and `sensitivity: base`;
- booleans use `false < true`;
- null and cell-status values are always last in both directions.

Formatted text is never parsed back. `900 MiB` sorts below `1.10 GiB`, and
`950 KiB/s` sorts below `2 MiB/s`.

Equal values MUST use a stable secondary order: the declared identity key, then
the original source row position. Pagination therefore remains stable after
repeated sorts.

### 12.3 Numeric locale

The artifact MUST declare `display.numeric_locale`; the initial default is
`en-US`. Numeric display and text collation use this value, not an implicit
browser locale. Browser timezone remains independent.

Tests inject the locale explicitly. Examples in this document use `en-US`; an
unscaled integer `30988` therefore displays as `30,988`, while `unit: count`
may select the adaptive representation defined in Section 10.1.

### 12.4 Precision

- all display rounding uses round-half-away-from-zero;
- raw integer quantities have no fractional part; an adaptive scaled display may
  contain a fractional magnitude while preserving the exact integer in detail;
- adaptive IEC values use the algorithm in Section 8.1;
- rates and timing values use at most three fractional digits;
- percentages use at most two fractional digits;
- ratios use at most three fractional digits;
- trailing fractional zeroes are removed;
- negative zero displays as zero;
- formatting never changes the raw artifact value.

## 13. Chart Rules

Chart points retain canonical base units. The chart renderer never receives
already scaled MiB, GiB, thousands, or percentages represented as strings.

- every series has a complete logical descriptor;
- series sharing an axis must have the same canonical unit or a centrally
  declared compatible conversion;
- stacked series require the identical canonical unit and quantity family;
- missing or invalid points remain null and are not interpolated as zero;
- a series whose complete collection window contains no non-zero datapoint is
  omitted from the artifact, legend, and tooltip; a required all-null series
  carrying invalid-coverage evidence is not treated as an all-zero series;
- rates use actual adjacent-snapshot duration;
- timestamp coordinates use UTC artifact instants and browser-local display.
- before passing sparse series to a shared-tooltip chart library, the renderer
  aligns them to the union of x coordinates using `null` placeholders; it must
  not substitute zero, and a tooltip omits a series whose selected point is
  null;
- column and bar charts treat snapshot timestamps as discrete ordered
  categories, format their labels as browser-local times, and disable the
  continuous-axis crosshair; tooltip identity is matched by the configured x
  value rather than a library-internal datapoint index;

When an exact integer chart point uses `decimal_string`, the renderer derives a
temporary plotting value only after selecting an axis scale. That approximation
is never written back to the artifact and never replaces the exact value used
by tooltips or evaluations.

### 13.1 Axis scaling

Each numeric axis selects one display scale for all ticks. For a byte axis, the
scale is chosen from the largest absolute finite axis bound after stacking. The
axis title includes the selected unit, for example `Write rate [MiB/s]`; tick
labels contain only scaled numbers.

An axis MUST NOT show one tick in KiB/s and another in GiB/s. Rescaling an axis
does not modify series points.

### 13.2 Tooltips

Tooltips use the shared formatter but MAY select the most readable adaptive
prefix per value. They also expose exact or higher-precision raw detail:

```text
185.07 MiB/s
exact: 194,060,000 B/s
```

A tooltip must not display `194060000 bytes/s`, `185.07 MB/s`, or bare
`185.07 M` as its primary value.

### 13.3 Legend and shared-tooltip ordering

By default, the renderer orders chart series in the legend by descending
arithmetic mean of their finite observed points. Missing points do not
participate in the average. Equal averages retain declaration order so
rendering remains stable. The series color remains bound to its declared
series, not to its position after sorting.

A chart with `series_order: configured` preserves declaration order. This is
required when order has visual semantics, especially stacked charts whose last
declared series must remain the top layer. The CPU utilization chart uses this
contract to keep `idle` above busy CPU states. The renderer applies no
item-name-specific exception.

For stacked column/bar charts, ECharts renders the first series at the bottom
and the last series at the top. The renderer therefore orders drawable series
by ascending arithmetic mean so the largest series is the top layer. The
legend receives the inverse display order and remains descending by mean.
Shared-tooltip rows remain independently sorted by the selected datapoint
value.

The interactive HTML legend wraps series into rows and shows at most six rows
at once. Additional rows remain available through a vertical scrollbar; the
legend must not degrade into a single horizontally paginated row. Image
exports use the complete legend and grow the exported chart vertically when
needed. Chart interaction provides selection zoom, explicit zoom in/out,
reset, and drag-pan over a zoomed range. A single Export menu provides SVG,
PNG, and CSV. SVG and PNG are rendered with a light export palette and white
background so labels remain readable regardless of the current report theme.

The chart title, Y-axis labels, Y-axis crosshair label, and tooltip values use
one scale calculated from the complete chart. Binary byte units use IEC
prefixes (`KiB`, `MiB`, and so on); count-like units use SI prefixes (`k`, `M`,
and so on). A tooltip must not independently choose a different scale for an
individual datapoint.

For a shared tooltip, rows are sorted independently at every selected x value
by descending datapoint value. Equal values retain the legend order. A series
without a finite point at the selected x value is omitted rather than shown as
zero. Tooltip content remains pointer-interactive so its vertical scrollbar can
be used when many non-zero series are present. This display ordering never
changes artifact series or point order.

## 14. Delta And Rate Contracts

Every cumulative-counter Delta item declares:

- `requires_collection: window_endpoints`;
- stable `key_refs`;
- all applicable `epoch_refs`;
- bounded SQL selection before rows enter backend memory for high-cardinality
  sources;
- deterministic source ordering and limit;
- complete descriptors for every result column.

### 14.1 Type preservation

- integer counter minus integer counter produces an exact integer Delta;
- integer counter divided by duration produces a decimal rate;
- decimal timing counter Delta remains decimal in its timing unit;
- calculation results are not rounded before artifact serialization;
- display precision never affects evaluation or sorting.

### 14.2 Validity granularity

- missing start/end row: omit the row and record `missing_start` or
  `missing_end` coverage;
- changed or missing required epoch: omit the whole row and record epoch
  coverage;
- invalid required key: omit the whole row and record invalid-key coverage;
- unavailable optional counter: keep the row, set only affected derived cells
  to null, and attach column/cell status;
- a counter that is legitimately inapplicable for some source rows MAY declare
  its derived table column or chart series `optional: true`; a null endpoint
  then leaves that cell or point null without invalidating independent values
  and without creating `invalid_value` coverage;
- an optional chart series with no finite value across the complete collection
  window is omitted rather than transported as an all-null series; a required
  all-null series is retained when its gaps carry invalid-coverage evidence;
- counter decrease with unchanged epoch: invalidate the affected counter cells,
  record `counter_decrease` per column, and keep independent valid counters;
- invalid interval duration: omit the whole row;
- a row with all valid derived counters equal to zero MAY be removed only when
  `drop_zero_rows: true`;
- null cells do not count as observed zeroes.

`interval_coverage` MUST provide overall row counts and per-derived-column
status counts so the report can distinguish Top-N churn, resets, and unavailable
counters.

## 15. Database Scope And Titles

Every non-OS item declares exactly one scope:

- `all_databases` renders `(All databases)`;
- `current_database` renders `(Only DB_NAME)`.

Current-database items hide a redundant top-level `datname`. All-database items
retain database identity when the source is per database. Hiding a column does
not remove its descriptor from the unified content document.

## 16. Automatic Evaluation

Severity evaluates raw typed values in canonical units.

- rules use machine column names, not labels;
- exact-integer thresholds use lossless integer comparison;
- byte thresholds are expressed in raw bytes;
- display scaling never changes a threshold;
- null, timeout, unsupported, and invalid Delta cells do not match numeric
  conditions;
- the current rule schema has no estimated-value opt-in, so automatic evaluation
  MUST NOT target a field whose resolved `quality` is `estimated`;
- obvious discrete failures may receive automatic severity;
- workload-dependent volume or rate receives no arbitrary global threshold
  without documented evidence;
- summary text names the quantity and display unit.

## 17. Versioning And Source Safety

- PostgreSQL 14 through 18 are the supported major versions for the current
  content schema;
- PostgreSQL variants expose the same logical meaning and canonical units even
  when physical columns differ.
- a missing source feature produces item `unsupported`;
- a missing version-specific column uses null cells and `column_statuses`;
- numeric zero placeholders for unavailable version fields are forbidden;
- all SQL is read-only and runs through an explicitly read-only connection;
- one report item owns one query, script, Python source, or metric source.

## 18. Validation Requirements

The following are normative acceptance requirements. The current validator
enforces the structural subset and the artifact validator enforces resolved
descriptor and encoding shape. Remaining semantic enforcement gaps are listed
in Section 19. Content validation MUST ultimately reject:

- a displayed field without a complete logical descriptor;
- unknown value kinds, semantic roles, units, encodings, or quality values;
- incompatible `value_kind`, unit, and encoding combinations;
- `unit` together with `unit_ref`;
- a missing or invalid unit-ref target;
- a counter transform applied to a gauge or estimate;
- byte columns pre-scaled in SQL or declared as MB/GB;
- integer counter Delta output declared as a floating value without documented
  source semantics;
- chart series and axis unit disagreement;
- stacked series with incompatible quantity or unit;
- default sorting by a missing or formatted-only field;
- mixed numeric and explanatory text cells;
- numeric version placeholders;
- scope-title contract violations;
- non-finite numbers;
- rows whose encoded values violate their descriptors.

Artifact validation MUST verify column descriptors, cell encodings,
`cell_statuses`, `column_statuses`, nullability, timestamp form, and row width.

Unit tests MUST cover:

- exact integers at and beyond the JSON safe-integer boundaries;
- every IEC boundary, rounding promotion, sign, and zero;
- no fractional raw byte, block, or count values;
- byte-rate formatting;
- integer-safe sorting and stable tie ordering;
- sorting across adaptive display scales;
- fixed numeric locale and independent browser timezone;
- timestamp UTC normalization and exact-value preservation;
- null, zero, timeout, unsupported, and empty-string distinctions;
- row-dependent unit refs;
- estimated-value presentation and exclusion from automatic evaluation while no
  validated opt-in contract exists;
- table/chart formatter equivalence;
- Delta reset, counter-decrease, optional-column, and endpoint behavior;
- JSON raw values remaining unchanged by rendering.

Browser screenshots are not required. Unit tests and JSON artifact assertions
are authoritative.

## 19. Current Implementation Status And Remaining Migration

Schema version 4 already provides the unified content document, resolved table
and chart descriptors, cell and column statuses, lossless `decimal_string`
transport, BigInt browser sorting, shared unit formatting, UTC timestamp
normalization, row-dependent unit references, and explicit rejection of
unsupported artifact schema versions.

By default, the artifact embeds complete item source metadata, instructions,
the unified content document, and source provenance. The opt-in `--strip-meta`
representation keeps collected results and only the presentation metadata
needed to render them. It clears item source identifiers and text,
instructions, source catalogs, and item-level provenance, records
`runtime.strip_meta: true`, and retains the presentation unit registry required
for schema validation. The stripped HTML must not render source, instruction,
or metadata action buttons.

Known gaps remain in metric-table typing and in enforcement of some semantic
requirements:

- A number of existing integer counter Delta columns are still declared as
  `pg_type: float8`. The metric engine subtracts endpoint values before
  rendering, but the floating output declaration selects a decimal JSON
  descriptor and therefore does not guarantee the exact-integer transport
  required by Sections 4 and 14.1. New integer counter Delta columns MUST use an
  integral output type such as `int8`; rates and genuinely fractional timing
  Delta values remain decimal.
- Timestamp normalization converts parseable timezone-aware values to UTC, but
  the current artifact validator does not validate the RFC 3339 form of every
  timestamp-valued table cell. Invalid text can therefore remain verbatim and a
  missing table-context timestamp can suppress the time label instead of
  automatically producing the Section 11 diagnostic.
- The current evaluation schema has no estimated-value opt-in, and validation
  does not yet cross-check rule columns against their resolved `quality`.
  Existing content must keep estimated fields out of automatic rules.

Migration completion requires:

1. Inventory existing `transform: delta` metric-table columns and classify their
   source semantics as integral counters or decimal measurements.
2. Change integral counter Delta declarations to an integral `pg_type` and
   verify `value_kind: integer` plus `encoding: decimal_string` in generated
   artifacts.
3. Add semantic validation which rejects floating declarations for integral
   counter Delta outputs while allowing documented decimal timing counters.
4. Validate and normalize every timestamp-valued artifact cell, with an explicit
   diagnostic or status for invalid and missing required instants.
5. Keep estimated-quality fields out of automatic evaluation until a versioned,
   validated opt-in field is implemented and enforce that restriction during
   validation.
6. Regenerate a load-test report and validate every table column and chart
   series from JSON, including values beyond the JavaScript safe-integer range.

Until these steps are complete, `pg-diag validate` is necessary but not
sufficient evidence that legacy content satisfies every semantic requirement in
this document. Adding any new numeric or temporal field without a complete
effective descriptor remains prohibited.
