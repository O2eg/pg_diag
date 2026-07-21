# PostgreSQL Access Best Practices

This guide describes secure and operationally correct ways to connect
`pg_diag` to standalone PostgreSQL servers and high-availability clusters. It
covers database credentials, SSH access, TLS boundaries, connection poolers,
and a Patroni deployment behind HAProxy.

All host names, database names, users, and non-standard ports in the examples
are illustrative. Names under `example.net` are reserved for documentation.
Adapt the examples to the effective `pg_hba.conf`, network policy, TLS setup,
and failover design of the target environment.

## Core principles

1. Use a dedicated PostgreSQL login role rather than a superuser or an
   application role.
2. Give that role `CONNECT` only to the databases in scope and add catalog or
   extension privileges only when a selected report item requires them.
3. Prefer direct TLS with server-name verification for database-only
   collection.
4. Use SSH mode only when host evidence is required or direct database access
   is unavailable. Pin the SSH host key and use a dedicated SSH account.
5. Treat the database endpoint and the host being inspected as separate
   concerns. This distinction is especially important in Patroni clusters.
6. Avoid transaction poolers unless their startup-parameter and session
   behavior has been explicitly validated with `pg_diag`.
7. Protect the generated report as sensitive operational data.

## Collection modes and trust boundaries

| `--collection-mode` | PostgreSQL connection | Host evidence | Intended use |
|---|---|---|---|
| `remote-db-only` | Direct TCP or Unix socket from the collector | Not collected | Safest default for a remote database |
| `local` | Direct TCP or Unix socket from the collector | Collected from the collector host | Run on the PostgreSQL host |
| `remote` | TCP through a dynamic local SSH forward | Collected from the SSH target | Full remote database and host diagnosis |

```text
REMOTE-DB-ONLY

  Collector host                                  Database endpoint
  +-----------------------------+                 +-----------------------+
  | OS user: diagnostics runner | -- TLS/TCP ---->| PostgreSQL or HAProxy |
  | DB role: pg_diag            |   :5432/:5000   | DB auth: SCRAM        |
  +-----------------------------+                 +-----------------------+

  SSH: none
  Host evidence: none


LOCAL

  PostgreSQL host
  +-----------------------------------------------------------------------+
  | OS user: pg_diag_os                                                   |
  | pg-diag --collection-mode local                                       |
  |    |                                                                  |
  |    +-- TCP 127.0.0.1:5432 + SCRAM ---------------------+               |
  |    |                                                    |               |
  |    +-- /var/run/postgresql/.s.PGSQL.5432 + peer -------+               |
  |                                                         v               |
  |                                                   PostgreSQL            |
  | Host probes inspect this operating system                              |
  +-----------------------------------------------------------------------+


REMOTE

  Collector host                         SSH target
  +-----------------------------+         +-------------------------------+
  | OS user: diagnostics runner |         | sshd :22                     |
  | DB role: pg_diag            | ==SSH=> | SSH user: pg_diag_ssh        |
  | asyncpg ->                  | tunnel  | auth: key + known_hosts      |
  | 127.0.0.1:<dynamic-port>    |         |   +-- host probes            |
  +-----------------------------+         |   +-- TCP -> <db-host>:5432  |
                                          +----------------+--------------+
                                                           |
                                                           v
                                                      PostgreSQL
                                                      auth: SCRAM
```

In `local` mode, host evidence describes the machine on which `pg_diag` runs.
In `remote` mode, it describes `--ssh-host`. A successful database connection
does not prove that the inspected host is the host serving that connection.

## Controls applied by pg_diag

Every PostgreSQL session opened by `pg_diag` requests these startup settings:

- `default_transaction_read_only=on`;
- `statement_timeout=1000` (one second);
- `lock_timeout=1000`;
- `idle_in_transaction_session_timeout=10000`;
- `search_path=pg_catalog, public`.

The collector verifies that the session is read-only before collection and
uses explicit read-only transactions for its main SQL executor. A query that
cannot finish within one second is reported as an item-level error; increasing
the timeout globally is usually worse than disabling or optimizing that item.

These controls reduce the risk of an accidental write by `pg_diag`. They do
not make a privileged credential safe: anyone who obtains the password can
open another session without these guards.

Content packs are executable input. SQL, shell sources, and trusted Python
sources can access the database or operating system with the privileges of the
collector accounts. Use only reviewed content and keep those accounts
least-privileged.

## Recommended accounts

### Dedicated PostgreSQL role

The preferred role has `LOGIN`, membership in `pg_monitor`, and `CONNECT` only
to databases that must be diagnosed:

```sql
CREATE ROLE pg_diag LOGIN PASSWORD '<managed-secret>';
GRANT pg_monitor TO pg_diag;
GRANT CONNECT ON DATABASE application_db TO pg_diag;
ALTER ROLE pg_diag SET default_transaction_read_only = on;
```

Manage the role, grants, password rotation, and revocation through the
environment's configuration-management and secret-management systems. Do not
put the real password in an interactive SQL command or shell history.

PostgreSQL grants `CONNECT` to `PUBLIC` by default. An explicit `GRANT CONNECT`
therefore documents the intended database but does not, by itself, prevent the
role from connecting to other databases. Enforcing that boundary requires a
database-wide ACL policy, commonly revoking `CONNECT` from `PUBLIC` and
granting it to approved roles, plus matching HBA rules. Do not introduce such
a revocation on an existing system without assessing every application role.

`pg_monitor` improves visibility into activity and statistics, but it is not a
promise that every optional item will succeed. Extensions installed in custom
schemas may require narrowly scoped `USAGE ON SCHEMA` and `EXECUTE` grants.
Security-sensitive data such as password hashes should remain unavailable to
the diagnostics role unless there is an explicit, reviewed requirement.

A host-based authentication rule for direct TLS might follow this template:

```text
hostssl  application_db  pg_diag  <collector-cidr>  scram-sha-256
```

Place it according to the effective HBA ordering and restrict the source
network. A TCP forward does not turn a TCP connection into a local
peer-authenticated connection; TCP still follows the matching `host` or
`hostssl` rule.

To revoke access immediately while preserving the role for investigation:

```sql
ALTER ROLE pg_diag NOLOGIN;
```

### Dedicated SSH account

For `remote` mode, use a non-root account such as `pg_diag_ssh` with:

- public-key authentication only;
- read access only to the host files and `/proc` data required by selected
  items;
- permission to execute the required read-only commands and use SFTP;
- local TCP forwarding restricted to approved database endpoints where the
  SSH server supports such restrictions;
- no general-purpose `sudo`; `pg_diag` only attempts `sudo -n` for `lshw` when
  it is already permitted.

The SSH account and PostgreSQL role are independent identities and do not need
the same name.

### Existing monitoring roles

Reusing an exporter role can work, but it couples two tools to one credential
and privilege lifecycle. Exporters often use Unix-socket peer authentication
and may not have a password, so the same role may not work through TCP/SCRAM.
A dedicated `pg_diag` role is easier to audit and revoke.

### Superuser access

Do not use the `postgres` role for routine diagnostics. A time-limited
superuser credential can be an emergency fallback when complete evidence is
more important than least privilege, but it should require explicit approval,
controlled delivery, rapid rotation, and protected report storage.

## Credentials and report handling

Prefer a PostgreSQL passfile over `--password`, a password embedded in a DSN,
or a long-lived `PGPASSWORD` variable:

```text
db.example.net:5432:application_db:pg_diag:<secret>
```

```bash
chmod 600 ~/.pgpass
```

Password-source priority is:

1. `--password` or a password in the DSN;
2. `PGPASSWORD`;
3. `--passfile`, DSN `passfile`, `PGPASSFILE`, then `~/.pgpass`.

In `remote` mode, the passfile entry must match the original `--host` and
`--port` as seen from the SSH target, not the dynamic loopback port created on
the collector. Escape `:` as `\:` and `\` as `\\` inside passfile fields.

Protect SSH private keys and PostgreSQL passfiles from group and other access.
Obtain the SSH host-key fingerprint over an independent trusted channel before
adding it to `known_hosts`; `ssh-keyscan` alone does not authenticate a host.

Reports may contain object names, queries, configuration, filesystem paths,
and infrastructure evidence. Keep report files access-controlled, encrypt
them in transit and at rest where required, and define a retention period.

## Recommended connection patterns

### Direct database-only access

Use this pattern when operating-system evidence is not required. It supports a
normal end-to-end TLS identity check and has the smallest trust surface.

```text
  Collector                                      PostgreSQL service
  +-------------------------+                    +------------------------+
  | OS user: diag runner    |                    | db.example.net:5432    |
  | DB role: pg_diag        | -- TLS/SCRAM ----> | certificate name:      |
  | no SSH privileges       |   verify-full      | db.example.net         |
  +-------------------------+                    +------------------------+
```

```bash
pg-diag snapshots \
  --collection-mode remote-db-only \
  --dsn "postgresql://pg_diag@db.example.net:5432/application_db?sslmode=verify-full" \
  --passfile ~/.pgpass \
  --duration-seconds 900 \
  --interval-seconds 60 \
  --out reports/application_db
```

The certificate chain, certificate name, HBA rule, and network policy must all
match the service endpoint.

### Full remote collection over SSH

Use this pattern when database and host evidence are both needed from one
known PostgreSQL node.

```text
  Collector                                  PostgreSQL host
  +-------------------------+                +---------------------------+
  | DB role: pg_diag        |                | sshd db-node.example.net  |
  | passfile entry matches: | == SSH :22 ==> | SSH user: pg_diag_ssh    |
  | 127.0.0.1:5432          | key + host key | host probes run here      |
  | asyncpg -> dynamic port |                |         |                 |
  +-------------------------+                |         v                 |
                                             | PostgreSQL 127.0.0.1:5432 |
                                             | SCRAM role: pg_diag       |
                                             +---------------------------+
```

```text
127.0.0.1:5432:application_db:pg_diag:<secret>
```

```bash
pg-diag snapshots \
  --collection-mode remote \
  --ssh-host db-node.example.net \
  --ssh-port 22 \
  --ssh-user pg_diag_ssh \
  --ssh-key ~/.ssh/pg_diag_ed25519 \
  --ssh-known-hosts ~/.ssh/pg_diag_known_hosts \
  --host 127.0.0.1 \
  --port 5432 \
  --database application_db \
  --user pg_diag \
  --passfile ~/.pgpass \
  --duration-seconds 900 \
  --interval-seconds 60 \
  --out reports/application_db
```

SSH encrypts the collector-to-SSH-host segment. If `--host` points from that
host to another server or proxy, the second segment has its own TLS and network
security requirements.

PostgreSQL HBA evaluates the address that opens the server-side database
connection. For a forward to `127.0.0.1:5432`, this is normally a loopback
connection from the SSH target, not the collector's network address.

Remote mode rejects `sslmode=verify-full` because asyncpg connects to the
dynamic local address `127.0.0.1`, which prevents verification of the original
database hostname. Use direct database connectivity when hostname verification
is mandatory.

### Local Unix-socket access with peer authentication

This is a good passwordless pattern when `pg_diag` is installed on the database
host and a dedicated operating-system account maps to the PostgreSQL role.

```text
  PostgreSQL host
  +---------------------------------------------------------------------+
  | systemd/sudo -> OS user: pg_diag                                    |
  |                      |                                              |
  |                      v                                              |
  |             pg-diag --collection-mode local                         |
  |                      |                                              |
  |                      +-- host probes                                |
  |                      |                                              |
  |                      v                                              |
  |          /var/run/postgresql/.s.PGSQL.5432                          |
  |                      | peer                                         |
  |                      v                                              |
  |          PostgreSQL role: pg_diag                                   |
  +---------------------------------------------------------------------+
```

```bash
sudo -u pg_diag pg-diag snapshots \
  --collection-mode local \
  --host /var/run/postgresql \
  --port 5432 \
  --database application_db \
  --user pg_diag \
  --duration-seconds 900 \
  --interval-seconds 60 \
  --out reports/application_db
```

Keep the OS account non-interactive and launch it through a controlled service
or automation mechanism. Installation, upgrades, report retrieval, and node
selection become operational responsibilities.

### Patterns to avoid

Do not forward a local TCP socket to a remote Unix socket merely to reuse peer
authentication. PostgreSQL sees the OS identity of the process opening the
remote socket, normally the SSH account, rather than the collector's local
user. Authentication fails unless that identity is deliberately mapped to the
requested database role, which adds unnecessary coupling and privilege.

Avoid PgBouncer `auth_type=trust`. It weakens client authentication, and a
pooler may reject, discard, or reapply startup and session parameters such as
read-only mode, timeouts, and `search_path`. If a pooler is unavoidable, test
the exact pool mode and configuration, verify the effective settings after
checkout, and prefer a transparent TCP proxy for diagnostics.

## Patroni and HAProxy

A Patroni cluster introduces two different questions:

1. Which PostgreSQL instance is the writable primary for database evidence?
2. Which operating-system node should host probes inspect?

A primary-routing proxy answers the first question but not necessarily the
second.

### Database-only diagnosis of the current primary

For database-only collection, a stable HAProxy endpoint whose backend health
check uses the Patroni REST API is usually the best target. The ports below are
examples; use the effective HAProxy configuration.

```text
                               Patroni cluster
                          +--------------------------+
                          | db-1 :5432  PRIMARY     |
  Collector               | Patroni REST :8008      |
  +------------------+    +-------------^------------+
  | DB role: pg_diag |                  |
  | no SSH           |                  | selected by /primary or /master
  +--------+---------+                  |
           |                            |
           | TLS/SCRAM                  |
           v                            |
  +--------------------------+          |
  | HAProxy                  +----------+
  | db-primary.example.net   |
  | primary frontend :5000   |          +--------------------------+
  | replica frontend :5001   |          | db-2 :5432  REPLICA     |
  +--------------------------+          | Patroni REST :8008      |
                                        +--------------------------+
```

```text
db-primary.example.net:5000:application_db:pg_diag:<secret>
```

```bash
pg-diag snapshots \
  --collection-mode remote-db-only \
  --dsn "postgresql://pg_diag@db-primary.example.net:5000/application_db?sslmode=verify-full" \
  --passfile ~/.pgpass \
  --duration-seconds 900 \
  --interval-seconds 60 \
  --out reports/patroni_primary
```

Validate all of the following before relying on this path:

- the frontend selects exactly one Patroni primary using the intended REST
  health endpoint;
- HAProxy health-check intervals and failover behavior meet the diagnostic
  workflow's requirements;
- the PostgreSQL TLS certificate is valid for the service name used by the
  collector when `verify-full` is enabled;
- Layer 4 TLS pass-through reaches PostgreSQL with the service name on its
  certificate, or every TLS termination and re-encryption boundary is
  separately authenticated;
- the HAProxy-to-PostgreSQL network segment is protected as required;
- a connection drop or server identity change during switchover is treated as
  a failed or partial run, not silently merged into one timeline.

Do not use the PostgreSQL port of an arbitrary node when the intent is to
diagnose the current primary. After a switchover, that endpoint may be a
replica. Conversely, use an explicitly replica-only frontend only when replica
diagnosis is intended.

### Full diagnosis of the current primary host

For a report that combines primary database data with primary host evidence,
resolve the current leader through a trusted control plane immediately before
the run, SSH to that node, and connect to its local PostgreSQL port:

```text
  Trusted leader lookup
  (orchestrator / service discovery)
                 |
                 | resolves db-1.example.net
                 v
  Collector                              Current Patroni leader
  +-------------------------+            +-----------------------------+
  | DB role: pg_diag        | ==SSH:22=> | SSH user: pg_diag_ssh      |
  | dynamic local DB port   |            | host probes inspect db-1   |
  +-------------------------+            |            |                |
                                         |            v                |
                                         | PostgreSQL 127.0.0.1:5432   |
                                         +-----------------------------+
```

This topology still cannot make a long-running report atomic with respect to a
Patroni switchover. Confirm the member is still primary after opening the
database connection, record the resolved member and role, monitor for
connection loss or timeline changes, and rerun the collection after failover
when a single-primary-host interpretation is required.

Do not SSH to an HAProxy host or a fixed Patroni member and assume that its OS
metrics belong to the PostgreSQL primary selected by HAProxy. The database and
host portions can then describe different machines.

### Cluster-wide evidence

One `pg_diag` run represents one database connection and at most one host. For
a cluster-wide investigation, orchestrate separate runs:

- one database-only report through the primary endpoint;
- one local or remote host report for each Patroni member;
- optional database-only reports through explicitly replica-targeted
  endpoints.

Keep run identifiers and timestamps so the reports can be correlated without
pretending they are one transactionally consistent snapshot.

### Patroni topology decision table

| Goal | Database endpoint | Host evidence | Recommended mode |
|---|---|---|---|
| Current primary database only | HAProxy primary service | None | `remote-db-only` |
| A specific member, database only | Member `:5432` | None | `remote-db-only` |
| Current primary database and its OS | Resolved leader `127.0.0.1:5432` through SSH | Resolved leader | `remote` |
| One member's database and OS | That member `127.0.0.1:5432` through SSH | Same member | `remote` |
| Entire cluster | Multiple explicit endpoints | Every member separately | Orchestrate multiple runs |
| Primary through HAProxy plus fixed SSH host | HAProxy-selected primary | Fixed SSH host | Avoid: evidence may refer to different nodes |

## Preflight checklist

- [ ] The selected collection mode matches the required database and host
      evidence.
- [ ] A dedicated PostgreSQL role is used and has `CONNECT` only where needed.
- [ ] Optional grants were added only after reviewing item-level permission
      failures.
- [ ] The effective HBA rule requires the intended authentication method.
- [ ] The passfile and private key are not accessible to group or other users.
- [ ] The SSH host key was verified through an independent trusted channel.
- [ ] `--host` and `--port` are reachable from the collector in direct mode or
      from the SSH target in remote mode.
- [ ] TLS identity and encryption are checked for every network segment.
- [ ] A pooler is bypassed unless its exact session behavior has been tested.
- [ ] In Patroni, the primary-routing health check and failover behavior were
      verified against the effective HAProxy configuration.
- [ ] In Patroni, the SSH target and the database-serving node are known to be
      the same when interpreting combined database and host evidence.
- [ ] The report output directory and retention policy match the sensitivity of
      the collected evidence.
- [ ] Item-level errors, timeouts, unsupported items, and incomplete evidence
      are reviewed after the run.
