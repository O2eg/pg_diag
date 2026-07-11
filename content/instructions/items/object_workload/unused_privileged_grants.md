# Unused Privileged Grants

This item lists powerful table privileges on tables with no observed activity since statistics reset.

## What this item shows
- Table, grantee, privilege, and grant option flag.
- Read and write activity counters from `pg_stat_user_tables`.

## Automatic evaluation
- Severity is `unknown`: zero cumulative table activity cannot prove that a privilege is unused.
- `stats_reset` defines the observation start, and standby, failover, seasonal, or maintenance paths may be absent.
- Results are bounded to 1000 grants.

## Checklist
- Treat findings as revoke candidates, not proof of unused access.
- Check the reported `stats_reset` before acting.
- Revoke stale write privileges after application-owner confirmation.
