# PostgreSQL Binary Permissions

This instruction belongs to report item `os.postgres_binary_integrity`.
It is backed by local Python source `security.postgres_binary_integrity`.

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

## Related report items
- [backend_os.postgres_main_process_linked_libraries](#item-backend_os.postgres_main_process_linked_libraries) — Inspect dependencies of the running PostgreSQL executable.
- [overview.server_version](#item-overview.server_version) — Confirm the expected server build.
- [os.extension_directory_permissions](#item-os.extension_directory_permissions) — Review other executable code loaded by PostgreSQL.

## Checklist
- Keep binaries owned by root or postgres.
- Remove group/world write permissions.
- Reinstall packages if executable integrity is uncertain.
