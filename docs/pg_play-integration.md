# pg_play integration contract

This document is for orchestrator authors. Normal users retain the report,
render, inspect, and collection CLI documented in the README.

`pg_diag` supports the hidden `pg_play/component/v1` machine transport:

```bash
pg-diag --machine --request-id diag-001 --component-capabilities
pg-diag --machine --request-id diag-002 explain-plan \
  --pg-version 180000 --run-mode snapshots --collection-mode remote-db-only
pg-diag --machine --request-id diag-003 validate-artifact report.json
pg-diag --machine --request-id diag-004 summarize report.json
```

One-shot and snapshots collection commands also return the common machine
envelope. Report files are described by paths and SHA-256 hashes. Partial
collection remains `partial`; it is not promoted to success merely because a
JSON artifact exists.

`summarize` validates the artifact schema before returning deterministic
counts, completeness, severities, collection statuses, and snapshot count.
It does not interpret findings or apply remediation.
