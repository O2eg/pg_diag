# Relation Cache Coverage

## What this item shows
- Cached percentage of each selected relation's current on-disk size.
- Coverage calculated with PostgreSQL `block_size` rather than a fixed block size.

## What to watch
- Coverage loss for frequently accessed relations during cache churn.

## Common fault causes
- Competing working sets, bulk scans, relation growth, or truncation.

## Automatic evaluation
- No severity is assigned. Small relations can legitimately approach 100 percent.

## Checklist
- Compare similarly sized relations.
- Remember that relation growth changes the denominator.
