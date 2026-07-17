# Dirty And Pinned Buffers

## What this item shows
- Dirty buffers and buffers pinned by one or more backends.
- Two overlapping gauges that must not be summed.

## Units
- `blocks` counts dirty or pinned shared-buffer slots/pages. One block uses the server's configured `block_size`; `kblocks` and `Mblocks` are SI-scaled block counts.

## What to watch
- Sustained dirty growth or prolonged pinned-buffer growth.

## Common fault causes
- Heavy DML, slow writeback, or checkpoint pressure.
- Long-running operations holding buffer pins.

## Automatic evaluation
- No severity is assigned because workload and pool size determine acceptable levels.

## Checklist
- Correlate with sessions, waits, checkpoints, and PostgreSQL I/O.
- Do not add the two lines; a buffer can be both dirty and pinned.
