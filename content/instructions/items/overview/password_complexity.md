# Password Complexity

This item reports missing password complexity hooks in `shared_preload_libraries`.

## What this item shows
- Whether `passwordcheck` or `credcheck` is preloaded.
- Whether related extensions are installed or available.
- Current `shared_preload_libraries` value for context.

## Checklist
- Use `passwordcheck`, `credcheck`, or an equivalent password policy mechanism for local PostgreSQL passwords.
- Add the chosen module to `shared_preload_libraries` and restart PostgreSQL when required.
- Keep extension installation consistent across databases where password management occurs.
