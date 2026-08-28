# Unvalidated Constraints

This instruction belongs to report item `indexes.unvalidated_constraints`. The item is backed by `indexes.unvalidated_constraints` (SQL query).

## What this item shows
- CHECK and FOREIGN KEY constraints created or altered with NOT VALID and never validated afterwards.
- The full constraint definition and, for foreign keys, the referenced table.
- Only new and updated rows are checked by a NOT VALID constraint; existing rows may already violate it.

## What to watch
- Foreign keys left NOT VALID after an online migration: orphaned rows can accumulate unnoticed.
- Old NOT VALID constraints whose validation step was forgotten, not postponed.
- The planner cannot use an unvalidated constraint for optimizations such as partition pruning by CHECK.

## Common fault causes
- Online migrations that add constraints as NOT VALID and skip the follow-up VALIDATE CONSTRAINT.
- Deploy scripts interrupted between ADD CONSTRAINT and VALIDATE.

## Automatic evaluation
- Every unvalidated constraint reports `medium`; the list covers the first 1000 constraints and marks truncation.

## Related report items
- [indexes.foreign_keys_without_index](#item-indexes.foreign_keys_without_index) — Foreign keys whose validation and cascades are slow for a different reason.
- [indexes.invalid_indexes](#item-indexes.invalid_indexes) — Indexes left invalid by interrupted DDL, the index-side analogue.

## Checklist
- Run VALIDATE CONSTRAINT during a low-traffic window; it takes only a SHARE UPDATE EXCLUSIVE lock.
- Before validating a foreign key, check for existing violating rows and clean them up.
