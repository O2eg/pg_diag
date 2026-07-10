# Extension Directory Permissions

This instruction belongs to `os.extension_directory_permissions`, backed by local Python source `security.extension_directory_permissions`.

## What this item shows
- Common PostgreSQL extension and library directories.
- Directories writable by group or other OS users.

## What to watch
- Group/world write access to control files or shared-library directories.

## Automatic evaluation
- World-writable paths are `high`; group-writable paths are `medium`.
- `unsupported` means no standard local extension directory was discovered. Custom install prefixes remain outside automatic coverage.

## Common fault causes
- Manual extension deployment, permissive package extraction, custom prefixes, or ownership drift during upgrades.

## Checklist
- Keep extension directories writable only by trusted package administrators.
- Review custom extension install paths.
- Reinstall extension packages if files were writable by untrusted users.
