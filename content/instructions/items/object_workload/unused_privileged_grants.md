# Unused Privileged Grants

This item lists powerful table privileges on tables with no observed activity since statistics reset.

## What this item shows
- Table, grantee, privilege, and grant option flag.
- Read and write activity counters from `pg_stat_user_tables`.

## Checklist
- Treat findings as revoke candidates, not proof of unused access.
- Check `stat_reset_times` before acting.
- Revoke stale write privileges after application-owner confirmation.
