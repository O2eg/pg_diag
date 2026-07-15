# PostgreSQL Main Process ldd Dependencies

This instruction belongs to report item `backend_os.postgres_main_process_linked_libraries`. The item is backed by the trusted Python source `backend.postgres_main_process_linked_libraries`.

## What this item shows
- A point-in-time `ldd` result for the executable of the PostgreSQL main process that owns the current pg_diag database backend.
- The database port, database name, backend PID, parent main-process PID, and resolved PostgreSQL executable path used for the check.
- The dependency name, resolved path, address printed by `ldd`, resolution status, and original `ldd` output line.
- The item runs once in both `one-shot` and `snapshots` modes; it is not sampled repeatedly during the snapshots window.

## Instance selection
- pg_diag obtains the exact server-side PID from `pg_backend_pid()` over its existing database connection.
- On the selected OS host it reads that process's `PPid` from `/proc/<backend_pid>/status`, verifies that both processes are PostgreSQL processes, and runs `ldd` against `/proc/<parent_pid>/exe`.
- This PID-to-parent chain selects the correct PostgreSQL instance even when several instances listen on different ports on the same host. The reported port and both PIDs provide evidence of that association.
- In `local` mode the collector must share the database host's PID namespace. In `remote` mode the PID lookup and `ldd` run on the SSH target. The item is not executed in `remote-db-only` mode.

## What to watch
- `link_status = not_found`, which means the dynamic linker could not resolve a declared dependency in the collection environment.
- A PostgreSQL executable path that does not match the expected package, version, or cluster deployment.
- Unexpected dependency paths, especially paths outside trusted system and PostgreSQL package directories.
- An unsupported result indicating that the connected backend PID is not visible on the selected host, `/proc` permissions are insufficient, or `ldd` is unavailable.

## Interpretation limits
- `ldd` reports how the executable's declared dynamic dependencies resolve. It is not a complete list of mappings currently loaded into process memory.
- Libraries loaded later with `dlopen()`, extension libraries loaded by individual backends, and mappings visible only in `/proc/<pid>/maps` may not appear here.
- `ldd_address` belongs to the loader invocation performed by `ldd`; it is not the address of that library in the already-running PostgreSQL main process. It commonly changes because of address-space randomization.
- `ldd` is executed only for the verified running PostgreSQL main-process executable, not for an arbitrary path supplied by the database.

## Checklist
- Confirm that `server_port`, `backend_pid`, and `postgres_main_pid` match the intended PostgreSQL instance.
- Compare `postgres_executable` with the expected PostgreSQL installation and major version.
- Investigate every `not_found` row and any dependency resolved from an unexpected directory.
- Use `/proc/<postgres_main_pid>/maps` when the diagnostic question is about mappings actually loaded at that moment rather than executable dependencies.

## Automatic evaluation
- This item is informational because the expected dependency set and trusted paths depend on the operating system and PostgreSQL build.
- Unresolved rows are preserved with `link_status = not_found` and produce a warning diagnostic, but they do not assign an automatic report severity.
