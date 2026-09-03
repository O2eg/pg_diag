# PostgreSQL Access Best Practices

This guide describes secure and operationally correct ways to connect
`pg_diag` to standalone PostgreSQL servers and high-availability clusters. It
covers database credentials, SSH access, TLS boundaries, connection poolers,
and a Patroni deployment behind HAProxy.

All host names, database names, users, and non-standard ports in the examples
are illustrative. Names under `example.net` are reserved for documentation.
Adapt the examples to the effective `pg_hba.conf`, network policy, TLS setup,
and failover design of the target environment.

## Table of contents

- [Core principles](#core-principles)
- [Collection modes and trust boundaries](#collection-modes-and-trust-boundaries)
- [Controls applied by pg_diag](#controls-applied-by-pg_diag)
- [Recommended accounts](#recommended-accounts)
  - [Dedicated PostgreSQL role](#dedicated-postgresql-role)
  - [Dedicated SSH account](#dedicated-ssh-account)
  - [Existing monitoring roles](#existing-monitoring-roles)
  - [Superuser access](#superuser-access)
- [Server log access (optional)](#server-log-access-optional)
- [Credentials and report handling](#credentials-and-report-handling)
- [Recommended connection patterns](#recommended-connection-patterns)
  - [Direct database-only access](#direct-database-only-access)
  - [Full remote collection over SSH](#full-remote-collection-over-ssh)
  - [Report collection through a jump host](#report-collection-through-a-jump-host)
    - [Database-only connection through a jump host](#database-only-connection-through-a-jump-host)
    - [Host and database connection through a jump host](#host-and-database-connection-through-a-jump-host)
  - [Local Unix-socket access with peer authentication](#local-unix-socket-access-with-peer-authentication)
  - [Patterns to avoid](#patterns-to-avoid)
- [Patroni and HAProxy](#patroni-and-haproxy)
  - [Database-only diagnosis of the current primary](#database-only-diagnosis-of-the-current-primary)
  - [Full diagnosis of the current primary host](#full-diagnosis-of-the-current-primary-host)
  - [Cluster-wide evidence](#cluster-wide-evidence)
  - [Patroni topology decision table](#patroni-topology-decision-table)
- [Preflight checklist](#preflight-checklist)

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

The table describes an unfiltered report. With `--item-id` or `--tags`,
`pg_diag` resolves each selected source's `targets`. A host-only selection does
not require PostgreSQL credentials and does not attempt a database connection.
In `remote` mode it still requires the SSH identity and host-key controls
described below, but no database tunnel is opened. If any selected executable
item targets `db`, the usual database connection requirements remain.

```text
REMOTE-DB-ONLY

  Collector host                                  Database endpoint
  +-----------------------------+                 +-----------------------+
  | OS user: diagnostics runner | -- TLS/TCP ---->| PostgreSQL or HAProxy |
  | DB role: pgdiag             |   :5432/:5000   | DB auth: SCRAM        |
  +-----------------------------+                 +-----------------------+

  SSH: none
  Host evidence: none


LOCAL

  PostgreSQL host
  +-----------------------------------------------------------------------+
  | OS user: pg_diag_os                                                   |
  | pg-diag --collection-mode local                                       |
  |    |                                                                  |
  |    +-- TCP 127.0.0.1:5432 + SCRAM ---------------------+              |
  |    |                                                    |             |
  |    +-- /var/run/postgresql/.s.PGSQL.5432 + peer -------+              |
  |                                                         v             |
  |                                                   PostgreSQL          |
  | Host probes inspect this operating system                             |
  +-----------------------------------------------------------------------+


REMOTE

  Collector host                         SSH target
  +-----------------------------+         +-------------------------------+
  | OS user: diagnostics runner |         | sshd :22                      |
  | DB role: pgdiag             | ==SSH=> | SSH user: pg_diag_ssh         |
  | asyncpg ->                  | tunnel  | auth: key + known_hosts       |
  | 127.0.0.1:<dynamic-port>    |         |   +-- host probes             |
  +-----------------------------+         |   +-- TCP -> <db-host>:5432   |
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
- `lock_timeout=750`;
- `idle_in_transaction_session_timeout=10000`;
- `search_path=pg_catalog, public`.

The collector verifies that the session is read-only before collection and
uses explicit read-only transactions for its main SQL executor. A query that
cannot finish within one second is reported as an item-level error unless its
manifest declares a different positive `timeout_ms`. A query may also declare
`lock_timeout_ms` when it needs a different lock-wait limit. Both overrides are
applied transaction-locally and `lock_timeout_ms` must stay below the effective
statement timeout so that lock waits remain distinguishable. Successful
overrides are restored to the runtime guards before the next query in a shared
snapshot transaction. Increasing the global timeouts is usually worse than
using narrow overrides, disabling the item, or optimizing the query.

The object-DDL post-processing phase uses its own bounded read-only transaction:
each DDLX catalog query has a five-second `statement_timeout`, while the complete
DDL extraction phase has a three-minute wall-clock limit. The transaction-local
override is discarded before the connection is used again.

These controls reduce the risk of an accidental write by `pg_diag`. They do
not make a privileged credential safe: anyone who obtains the password can
open another session without these guards.

Content packs are executable input. SQL, shell sources, and trusted Python
sources can access the database or operating system with the privileges of the
collector accounts. Use only reviewed content and keep those accounts
least-privileged.

## Recommended accounts

### Dedicated PostgreSQL role

The examples use `pgdiag` because PostgreSQL reserves the `pg_` prefix for
system roles. The reference grant set implemented by the
`pg_cluster/roles/pg_roles` Ansible role is:

- `LOGIN` with a managed SCRAM-SHA-256 password;
- membership in the predefined `pg_monitor` role;
- `CONNECT` on every existing connectable user database and on `template1`;
- role-level `default_transaction_read_only=on`;
- for each already installed `pg_stat_statements`, `pg_stat_kcache`,
  `pg_wait_sampling`, or `pg_buffercache` extension, `USAGE` on its actual
  schema;
- `SELECT` only on the allowlisted read-only extension views:
  `pg_stat_statements`, `pg_stat_statements_info`, `pg_stat_kcache`,
  `pg_wait_sampling_current`, `pg_wait_sampling_history`,
  `pg_wait_sampling_profile`, and `pg_buffercache`, when those objects belong
  to the corresponding installed extension;
- `EXECUTE` only on the allowlisted read-only functions
  `pg_stat_kcache()`, `pg_buffercache_pages()`,
  `pg_buffercache_summary()`, and `pg_buffercache_usage_counts()`, when those
  functions belong to the corresponding installed extension.

The role does not install or configure extensions. Missing extensions are
ignored. It does not grant access to application tables or sequences, bulk
privileges on extension schemas, or execution of statistics-reset functions.
This is the complete ready-made grant set; expand it only for a reviewed,
item-specific requirement.

```sql
CREATE ROLE pgdiag LOGIN PASSWORD '<managed-secret>';
GRANT pg_monitor TO pgdiag;
GRANT CONNECT ON DATABASE application_db TO pgdiag;
ALTER ROLE pgdiag SET default_transaction_read_only = on;
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
promise that every optional item will succeed. Apply the complete reference
grant set in every database to make supported, already installed diagnostic
extensions visible without granting application-data access. Security-sensitive
data such as password hashes should remain unavailable to the diagnostics role
unless there is an explicit, reviewed requirement.

A host-based authentication rule for direct TLS might follow this template:

```text
hostssl  application_db  pgdiag  <collector-cidr>  scram-sha-256
```

Place it according to the effective HBA ordering and restrict the source
network. A TCP forward does not turn a TCP connection into a local
peer-authenticated connection; TCP still follows the matching `host` or
`hostssl` rule.

To revoke access immediately while preserving the role for investigation:

```sql
ALTER ROLE pgdiag NOLOGIN;
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
A dedicated `pgdiag` role is easier to audit and revoke.

### Superuser access

Do not use the `postgres` role for routine diagnostics. A time-limited
superuser credential can be an emergency fallback when complete evidence is
more important than least privilege, but it should require explicit approval,
controlled delivery, rapid rotation, and protected report storage.

## Server log access (optional)

`pg-diag ... --log-depth-time-min` collects and parses the server `csvlog`
files for a bounded window. Log content is read by the collector process from
the filesystem — never through SQL file-access functions — so the setup below
is about PostgreSQL logging configuration and operating-system permissions.

### What NOT to grant

Do not give the `pgdiag` role `EXECUTE` on `pg_read_file()` /
`pg_read_binary_file()` and do not grant `pg_read_server_files`. The path
restriction to the data directory is not a protection: the data directory
contains the heap files of every table, including `pg_authid` with password
hashes, and these functions bypass all in-database privilege checks. `pg_diag`
never uses them and its log collection does not need them.

No additional database grants are required at all: the reference `pgdiag` role
already covers `pg_ls_logdir()`, `pg_current_logfile()`, and the
superuser-only settings `log_directory` / `data_directory` through
`pg_monitor` (which includes `pg_read_all_settings`).

### PostgreSQL logging configuration

```ini
logging_collector = on              # requires a restart
log_destination  = 'stderr,csvlog'  # sighup
log_directory    = '/var/log/postgresql'   # recommended outside the data directory
log_file_mode    = 0640             # sighup; REQUIRED for the ACL below to work
log_rotation_age  = 1d
log_rotation_size = 100MB
lc_messages = 'C'                   # or en_*; localized logs make pattern
                                    # matching unreliable and the items report
                                    # unsupported instead of a false "no errors"
```

### Filesystem permissions

Grant read access to the log directory with a POSIX ACL for the OS account
that runs the collector (`local` mode) or the dedicated SSH account
(`remote` mode):

```bash
setfacl -m  u:pg_diag_ssh:rX /var/log/postgresql          # directory traversal
setfacl -m  u:pg_diag_ssh:r  /var/log/postgresql/*.csv    # files that already exist
setfacl -dm u:pg_diag_ssh:r  /var/log/postgresql          # future rotated files
```

All three commands are required: the directory ACL alone grants traversal but
not the content of files created before it, and the default ACL applies only
to files created after it.

Why `log_file_mode = 0640` is mandatory: the ACL mask of a newly created file
is the default ACL mask AND-ed with the group bits of the creation mode. With
the default `log_file_mode = 0600` the group bits are zero, so the named-user
entry on every newly rotated file is masked to nothing and access silently
disappears after the first rotation. Verify after the next rotation:

```bash
getfacl /var/log/postgresql/postgresql-*.csv | grep effective
# no "#effective:---" lines may appear
```

Do not use group membership instead of the ACL: the `adm` group exposes all
system logs, and the `postgres` group on a cluster initialized with group
access (`initdb -g`, PostgreSQL 11+) exposes the whole data directory. If
`log_directory` stays inside the data directory, the account additionally
needs traverse (`--x`) on the data directory itself — moving logs outside is
cleaner.

### Verification

Smoke-check as the collector account:

```bash
sudo -u pg_diag_ssh sh -c \
  'f=$(ls /var/log/postgresql/*.csv | tail -1) && tail -c 4096 "$f" | head -c 200'
```

If the check fails with correct ACLs, inspect SELinux or AppArmor denials.

### Collection mode support

| Collection mode | Server log collection |
|---|---|
| `local` | Supported: the collector reads csvlog files directly |
| `remote` | Supported: an ephemeral POSIX-sh harvester filters logs on the SSH target (requires a shell-capable SSH account and standard tools: awk, tail, head, sed, cut, sort; a degraded probe reports `unsupported`) |
| `remote-db-only` | Not supported by design: there is no safe SQL path to log content |

## Credentials and report handling

Prefer a PostgreSQL passfile over `--password`, a password embedded in a DSN,
or a long-lived `PGPASSWORD` variable:

```text
db.example.net:5432:application_db:pgdiag:<secret>
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

Protect SSH private-key files, when used, and PostgreSQL passfiles from group
and other access.
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
  | DB role: pgdiag         | -- TLS/SCRAM ----> | certificate name:      |
  | no SSH privileges       |   verify-full      | db.example.net         |
  +-------------------------+                    +------------------------+
```

```bash
pg-diag snapshots \
  --collection-mode remote-db-only \
  --dsn "postgresql://pgdiag@db.example.net:5432/application_db?sslmode=verify-full" \
  --passfile ~/.pgpass \
  --duration-seconds 900 \
  --interval-seconds 60 \
  --out reports/application_db
```

The SSH identity can instead be supplied by an already running local agent:

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/pg_diag_ed25519

pg-diag one-shot \
  --collection-mode remote \
  --ssh-host db.example.net \
  --ssh-user pg_diag \
  --ssh-agent \
  --ssh-known-hosts ~/.ssh/pg_diag_known_hosts \
  --host 127.0.0.1 \
  --database application_db \
  --user pgdiag \
  --out reports/application_db
```

Agent mode is explicit, requires a live inherited `SSH_AUTH_SOCK`, and never
forwards the agent to the target. Keep strict `known_hosts` verification in
both key-file and agent modes.

The certificate chain, certificate name, HBA rule, and network policy must all
match the service endpoint.

### Full remote collection over SSH

Use this pattern when database and host evidence are both needed from one
known PostgreSQL node.

```text
  Collector                                  PostgreSQL host
  +-------------------------+                +---------------------------+
  | DB role: pgdiag         |                | sshd db-node.example.net  |
  | passfile entry matches: | == SSH :22 ==> | SSH user: pg_diag_ssh     |
  | 127.0.0.1:5432          | key + host key | host probes run here      |
  | asyncpg -> dynamic port |                |         |                 |
  +-------------------------+                |         v                 |
                                             | PostgreSQL 127.0.0.1:5432 |
                                             | SCRAM role: pgdiag        |
                                             +---------------------------+
```

```text
127.0.0.1:5432:application_db:pgdiag:<secret>
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
  --user pgdiag \
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

### Report collection through a jump host

Use the following patterns when the collector cannot reach the PostgreSQL host
directly but can reach an SSH jump host. The examples assume that PostgreSQL
and SSH run on the same target host and that PostgreSQL is reachable from that
host as `127.0.0.1:${PGDIAG_DB_PORT}`.

#### Database account prerequisite

Create the `pgdiag` database account before opening either tunnel. The
recommended `pg_cluster/roles/pg_roles` grant set is:

- `LOGIN` with a managed SCRAM-SHA-256 password;
- membership in `pg_monitor`;
- `CONNECT` on the databases in scope;
- `default_transaction_read_only=on`;
- conditional read-only access to already installed `pg_stat_statements`,
  `pg_stat_kcache`, `pg_wait_sampling`, and `pg_buffercache` objects, exactly
  as listed in [Dedicated PostgreSQL role](#dedicated-postgresql-role).

The Ansible role only creates the account and grants access. It does not
install an extension, grant access to application relations, or grant
statistics-reset functions.

#### Shared variables

Initialize these variables in every terminal that uses them. Replace all
placeholder values before running a command:

```bash
export PGDIAG_DB_USER_PASSWORD='***'
export PGDIAG_TARGET_HOST='DATABASE_HOST'
export PGDIAG_TARGET_JUMP_HOST='JUMP_HOST'
export PGDIAG_DB_NAME='postgres'
export PGDIAG_DB_USER='pgdiag'
export PGDIAG_DB_PORT='5005'
export PGDIAG_DB_FORWARDED_PORT='15005'
export MY_SSH_KEY='/path/to/private/key'
export PGDIAG_LOCAL_SSH_PORT='12225'
export PGDIAG_SSH_USER='debian'

export PGDIAG_REPORT_DIR='reports/CLUSTER_ID'

mkdir -p "$PGDIAG_REPORT_DIR"
```

Protect the private key and report directory according to the sensitivity of
the environment. A command-line `--password` is visible to processes that can
inspect the collector's arguments and may be retained in shell history; use a
passfile for routine automation.

#### Database-only connection through a jump host

This pattern exposes only the target PostgreSQL port on the collector. It does
not give `pg_diag` an SSH session on the database host and therefore does not
collect host evidence.

```text
pg-diag -> 127.0.0.1:${PGDIAG_DB_FORWARDED_PORT}
             |
             +-> jump ${PGDIAG_TARGET_JUMP_HOST}
                    |
                    +-> SSH host ${PGDIAG_TARGET_HOST}
                              |
                              +-> PostgreSQL 127.0.0.1:${PGDIAG_DB_PORT}
```

In the first terminal, load the key and keep the forwarding SSH process
running:

```bash
eval "$(ssh-agent -s)"
ssh-add "$MY_SSH_KEY"

ssh \
  -J "${PGDIAG_SSH_USER}@${PGDIAG_TARGET_JUMP_HOST}" \
  -N -T \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L "127.0.0.1:${PGDIAG_DB_FORWARDED_PORT}:127.0.0.1:${PGDIAG_DB_PORT}" \
  "${PGDIAG_SSH_USER}@${PGDIAG_TARGET_HOST}"
```

The apparent lack of output is expected: `-N -T` opens no shell and keeps the
foreground process alive solely to maintain the tunnel. Do not close this
terminal until collection has finished. The command uses the normal OpenSSH
host-key checks for both the jump host and target host; verify and pin those
keys before the run.

If PostgreSQL is not bound to loopback on the target host, replace the second
`127.0.0.1` in `-L` with the database address as it is reachable from
`${PGDIAG_TARGET_HOST}`. Do not make that substitution merely because the
target SSH host has a non-loopback address.

In the second terminal, initialize the shared variables and verify that the
forwarded endpoint answers:

```bash
pg_isready \
  --host 127.0.0.1 \
  --port "$PGDIAG_DB_FORWARDED_PORT" \
  --dbname "$PGDIAG_DB_NAME"
```

Expected output for the example port:

```text
127.0.0.1:15005 - accepting connections
```

`pg_isready` proves that a PostgreSQL server responds; it does not validate the
`pgdiag` password or grants.

Set a database that accepts the diagnostics role. Use `postgres` when the
application database name is not yet known:

```bash
export PGDIAG_DB_NAME='some_db_name'
```

Collect only the database inventory item to discover the databases visible to
the account:

```bash
pg-diag one-shot \
  --collection-mode remote-db-only \
  --host 127.0.0.1 \
  --port "$PGDIAG_DB_FORWARDED_PORT" \
  --database "$PGDIAG_DB_NAME" \
  --user "$PGDIAG_DB_USER" \
  --password "$PGDIAG_DB_USER_PASSWORD" \
  --output-format html \
  --html-out "${PGDIAG_REPORT_DIR}/${PGDIAG_DB_NAME}_$(date +%Y%m%d_%H%M%S).html" \
  --item-id overview.database_stats
```

Collect a complete current database snapshot without host evidence:

```bash
pg-diag one-shot \
  --collection-mode remote-db-only \
  --host 127.0.0.1 \
  --port "$PGDIAG_DB_FORWARDED_PORT" \
  --database "$PGDIAG_DB_NAME" \
  --user "$PGDIAG_DB_USER" \
  --password "$PGDIAG_DB_USER_PASSWORD" \
  --output-format html \
  --html-out "${PGDIAG_REPORT_DIR}/${PGDIAG_DB_NAME}_current_sn_$(date +%Y%m%d_%H%M%S).html"
```

#### Host and database connection through a jump host

Use this pattern when the report must include both database and operating
system evidence from `${PGDIAG_TARGET_HOST}`. The outer OpenSSH process exposes
the target host's SSH port locally. `pg_diag` then creates and manages its own
database forward inside that SSH connection.

```text
pg-diag
  -> SSH 127.0.0.1:${PGDIAG_LOCAL_SSH_PORT}
  -> jump ${PGDIAG_TARGET_JUMP_HOST}
  -> SSH ${PGDIAG_TARGET_HOST}:22
  -> PostgreSQL 127.0.0.1:${PGDIAG_DB_PORT}
```

In the first terminal, load the key and keep the SSH-port tunnel running:

```bash
eval "$(ssh-agent -s)"
ssh-add "$MY_SSH_KEY"

ssh \
  -N -T \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L "127.0.0.1:${PGDIAG_LOCAL_SSH_PORT}:${PGDIAG_TARGET_HOST}:22" \
  "${PGDIAG_SSH_USER}@${PGDIAG_TARGET_JUMP_HOST}"
```

This command also remains in the foreground without printing a success
message. An early exit or an `ExitOnForwardFailure` error means the local SSH
port was not established.

In the second terminal, initialize the shared variables. Because `pg_diag`
connects to the target SSH server through
`127.0.0.1:${PGDIAG_LOCAL_SSH_PORT}`, create a dedicated `known_hosts` file
whose host field matches that local endpoint:

```bash
export PGDIAG_TUNNEL_KNOWN_HOSTS="$HOME/.ssh/pg_diag_via_jump_known_hosts"

mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"

ssh-keyscan \
  -p "$PGDIAG_LOCAL_SSH_PORT" \
  127.0.0.1 > "$PGDIAG_TUNNEL_KNOWN_HOSTS"

test -s "$PGDIAG_TUNNEL_KNOWN_HOSTS" \
  && chmod 600 "$PGDIAG_TUNNEL_KNOWN_HOSTS" \
  && ssh-keygen -lf "$PGDIAG_TUNNEL_KNOWN_HOSTS"
```

Do not continue if `ssh-keyscan` produced an empty file or
`ssh-keygen -lf` could not parse it. `ssh-keyscan` retrieves a key but does not
authenticate it: compare the printed fingerprint with a value obtained from
the target host or another trusted channel. The key is the identity of
`${PGDIAG_TARGET_HOST}`, stored under the local forwarded endpoint.

Collect a full report with a 20-minute observation window and a 60-second
sampling interval:

```bash
pg-diag snapshots \
  --collection-mode remote \
  --duration-seconds 1200 \
  --interval-seconds 60 \
  --ssh-host 127.0.0.1 \
  --ssh-port "$PGDIAG_LOCAL_SSH_PORT" \
  --ssh-user "$PGDIAG_SSH_USER" \
  --ssh-key "$MY_SSH_KEY" \
  --ssh-known-hosts "$PGDIAG_TUNNEL_KNOWN_HOSTS" \
  --host 127.0.0.1 \
  --port "$PGDIAG_DB_PORT" \
  --database "$PGDIAG_DB_NAME" \
  --user "$PGDIAG_DB_USER" \
  --password "$PGDIAG_DB_USER_PASSWORD" \
  --output-format html \
  --html-out "${PGDIAG_REPORT_DIR}/${PGDIAG_DB_NAME}_full_$(date +%Y%m%d_%H%M%S).html"
```

Here `--host 127.0.0.1` is resolved from the target SSH host, not from the
collector. The host evidence therefore describes `${PGDIAG_TARGET_HOST}`, and
the database evidence describes PostgreSQL reached from that same target over
its loopback interface.

If the private key is passphrase-protected and already loaded into the agent,
replace `--ssh-key "$MY_SSH_KEY"` with `--ssh-agent`. Do not pass both options.

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
  |          PostgreSQL role: pgdiag                                    |
  +---------------------------------------------------------------------+
```

```bash
sudo -u pg_diag pg-diag snapshots \
  --collection-mode local \
  --host /var/run/postgresql \
  --port 5432 \
  --database application_db \
  --user pgdiag \
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
                          | db-1 :5432  PRIMARY      |
  Collector               | Patroni REST :8008       |
  +------------------+    +-------------^------------+
  | DB role: pgdiag  |                  |
  | no SSH           |                  | selected by /primary or /master
  +--------+---------+                  |
           |                            |
           | TLS/SCRAM                  |
           v                            |
  +--------------------------+          |
  | HAProxy                  +----------+
  | db-primary.example.net   |
  | primary frontend :5000   |          +--------------------------+
  | replica frontend :5001   |          | db-2 :5432  REPLICA      |
  +--------------------------+          | Patroni REST :8008       |
                                        +--------------------------+
```

```text
db-primary.example.net:5000:application_db:pgdiag:<secret>
```

```bash
pg-diag snapshots \
  --collection-mode remote-db-only \
  --dsn "postgresql://pgdiag@db-primary.example.net:5000/application_db?sslmode=verify-full" \
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
- a transient connection drop triggers at most five reconnection attempts,
  spaced three seconds apart;
- every replacement connection attempt and stale-connection close is bounded
  to five seconds;
- a reconnected session is accepted only when the database name, server
  version, recovery role, and server address still match the initial session;
  an identity change during switchover fails the run instead of silently
  merging two endpoints into one timeline.

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
  | DB role: pgdiag         | ==SSH:22=> | SSH user: pg_diag_ssh       |
  | dynamic local DB port   |            | host probes inspect db-1    |
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
- [ ] The passfile and any selected private-key file are not accessible to
      group or other users.
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
