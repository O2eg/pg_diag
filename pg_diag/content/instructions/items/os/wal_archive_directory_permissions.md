# WAL Archive Directory Permissions

This instruction belongs to `os.wal_archive_directory_permissions`, backed by local Python source `security.wal_archive_directory_permissions`.

## What this item shows
- Archive destination paths parsed from the command.
- Directory modes that expose or allow modification of archived WAL.

## What to watch
- World access, group write access, or a complex command for which no absolute destination can be inferred.

## Automatic evaluation
- World exposure is `high`; other broad permission findings are `medium`.
- Disabled archiving is `skipped/unknown` as not applicable. `archive_library`, an empty command, or a command without an inferable absolute path produces `unsupported`, never a false pass.

## Common fault causes
- Archive wrapper hides the destination, remote/object storage is used, a relative path depends on service cwd, or archive directory ownership drifted.

## Checklist
- Keep WAL archive directories restricted to PostgreSQL and backup automation.
- Avoid world-readable or writable archive paths.
- Verify command parsing manually for complex archive scripts.
