# PostgreSQL Binary Permissions

This instruction belongs to `os.postgres_binary_integrity`, backed by local Python source `security.postgres_binary_integrity`.

## What this item shows
- Visible PostgreSQL command paths such as `postgres`, `psql`, and backup tools.
- Group/world writable binaries.
- Unexpected binary owners.

## What to watch
- Group/world-writable executables or owners other than `root`/`postgres` for discovered paths.

## Automatic evaluation
- World-writable binaries are `high`; group-writable or unexpected-owner paths are `medium`.
- If no executable is discovered, the item is `unsupported`. This is a permission/ownership check, not package checksum, signature, or runtime integrity verification.

## Common fault causes
- Manual installation, extracted vendor archives, compromised package ownership, or PATH pointing to an unintended client binary.

## Checklist
- Keep binaries owned by root or postgres.
- Remove group/world write permissions.
- Reinstall packages if executable integrity is uncertain.
