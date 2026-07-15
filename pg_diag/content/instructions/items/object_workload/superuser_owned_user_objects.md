# Superuser-Owned User Objects

This item lists user-defined objects owned by PostgreSQL superusers.

## What this item shows
- Tables, sequences, views, foreign tables, and functions outside system schemas.
- Object owner and whether the owner is a superuser.
- Extension-owned objects are excluded.

## Automatic evaluation
- `medium` requests review because superuser ownership expands the impact of owner-controlled code and DDL.
- It is not automatically `high`: bootstrap or administrative ownership may be an intentional baseline exception.
- Results are bounded to 1000 objects.

## Checklist
- Move application objects to dedicated owner roles.
- Keep superuser ownership only for objects that truly require it.
- Recheck dependent grants after changing ownership.
