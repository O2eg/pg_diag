# Dirty Buffers By Usage Count

## What this item shows
- Dirty shared buffers grouped by clock-sweep usage count.
- Cold dirty pages separately from frequently reused dirty pages.

## What to watch
- Sustained low-usage dirty blocks and broad dirty growth.

## Common fault causes
- Burst DML, delayed writeback, or checkpoint pressure.

## Automatic evaluation
- No severity is assigned; a single sample is not diagnostic.

## Checklist
- Review several snapshots.
- Compare with checkpoint, background-writer, and storage-latency items.
