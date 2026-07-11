# Unix Socket Permissions

This item reports PostgreSQL Unix socket permissions that allow access by other OS users.

## What this item shows
- Configured `unix_socket_permissions`.
- Existing socket file mode when the socket is visible locally.
- Risk level for world-accessible socket permissions.

## Automatic evaluation
- `medium`: other OS users can attempt a Unix-socket connection.
- This is not an authentication bypass: matching `local` pg_hba rules still decide database access.
- Abstract sockets cannot be checked with filesystem permissions and are skipped.

## Checklist
- Use `0700` or `0770` for `unix_socket_permissions` unless all local OS users are trusted.
- Keep socket directories owned and writable only by trusted users.
- Review local `pg_hba.conf` rules together with socket permissions.
