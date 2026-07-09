# pg_hba Broad Network Ranges

This item lists `pg_hba.conf` host rules with universal or overly broad address ranges.

## What this item shows
- Rules using `all`, `0.0.0.0/0`, or `::/0`.
- Very broad IPv4 or IPv6 CIDR ranges.
- Network scope and risk reason for each matching rule.

## Checklist
- Replace broad ranges with the smallest required CIDR ranges.
- Keep administrative access separate from application access.
- Combine broad client ranges only with strong authentication and TLS enforcement.
