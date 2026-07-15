# pg_hba Broad Network Ranges

This item lists `pg_hba.conf` host rules with universal or overly broad address ranges.

## What this item shows
- Rules using `all`, `0.0.0.0/0`, or `::/0`.
- Very broad IPv4 or IPv6 CIDR ranges.
- Network scope and risk reason for each matching rule.

## Automatic evaluation
- `high`: universal, IPv4 `/8` or broader, or IPv6 `/32` or broader ranges.
- `medium`: IPv4 `/16` or broader, or IPv6 `/64` or broader, excluding loopback.
- Hostnames, `samehost`, and `samenet` cannot be safely expanded without network context.

## Checklist
- Replace broad ranges with the smallest required CIDR ranges.
- Keep administrative access separate from application access.
- Combine broad client ranges only with strong authentication and TLS enforcement.
