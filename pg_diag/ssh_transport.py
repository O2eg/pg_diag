"""AsyncSSH transport for full remote PostgreSQL host collection."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import getpass
import math
import os
from pathlib import Path
import shlex
import ssl
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from .errors import CommandTimeoutError, PgDiagError
from .security import redact_error


REMOTE_OUTPUT_LIMIT = 32 * 1024 * 1024
DEFAULT_SSH_PORT = 22
DEFAULT_DB_PORT = 5432
REMOTE_PROCESS_STOP_GRACE_SECONDS = 0.25
REMOTE_SCRIPT_WRAPPER = r"""
exec 3<&0
if command -v setsid >/dev/null 2>&1; then
  setsid /bin/sh -s -- "$@" <&3 &
  child=$!
  kill_pid=-$child
else
  /bin/sh -s -- "$@" <&3 &
  child=$!
  kill_pid=$child
fi
exec 3<&-
terminate_group() {
  trap - TERM INT
  kill -TERM "$kill_pid" 2>/dev/null || true
  sleep 0.1
  kill -KILL "$kill_pid" 2>/dev/null || true
  exit 143
}
trap terminate_group TERM INT
wait "$child"
status=$?
trap - TERM INT
exit "$status"
"""


class MissingAsyncsshError(PgDiagError):
    pass


class SshTransportError(PgDiagError):
    pass


class SshCommandTimeoutError(SshTransportError, CommandTimeoutError):
    pass


@dataclass(frozen=True)
class SshConfig:
    host: str
    username: str
    client_key: Path
    known_hosts: Path
    port: int = DEFAULT_SSH_PORT
    connect_timeout: float = 10.0
    passphrase: str | None = field(default=None, repr=False)

    def validate(self) -> None:
        if not self.host.strip():
            raise SshTransportError("SSH host is required for remote collection")
        if not self.username.strip():
            raise SshTransportError("SSH user is required for remote collection")
        if not 1 <= int(self.port) <= 65535:
            raise SshTransportError("SSH port must be between 1 and 65535")
        if not math.isfinite(self.connect_timeout) or self.connect_timeout <= 0:
            raise SshTransportError("SSH connect timeout must be positive")
        client_key = self.client_key.expanduser()
        if not client_key.is_file():
            raise SshTransportError(f"SSH private key does not exist: {self.client_key}")
        if client_key.stat().st_mode & 0o077:
            raise SshTransportError(
                f"SSH private key must not grant group or other access: {self.client_key}"
            )
        if not self.known_hosts.expanduser().is_file():
            raise SshTransportError(f"SSH known_hosts file does not exist: {self.known_hosts}")


@dataclass(frozen=True)
class SshCommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class _RawCommandResult:
    returncode: int
    stdout: str | bytes
    stderr: str | bytes


@dataclass
class _OutputBudget:
    limit: int
    size: int = 0

    def consume(self, value: str | bytes) -> None:
        self.size += len(value if isinstance(value, bytes) else value.encode("utf-8"))
        if self.size > self.limit:
            raise SshTransportError("remote command output exceeds the 32 MiB limit")


def remote_database_endpoint(
    dsn: str | None,
    connection_kwargs: dict[str, Any],
) -> tuple[str, int]:
    """Resolve the DB endpoint as it is reachable from the SSH server."""
    explicit_host = connection_kwargs.get("host")
    explicit_port = connection_kwargs.get("port")
    if explicit_host:
        host = _single_tcp_host(str(explicit_host))
        return host, _valid_port(explicit_port or DEFAULT_DB_PORT, "PostgreSQL")

    if dsn:
        parsed = urlsplit(dsn)
        if parsed.scheme in {"postgres", "postgresql"} and parsed.hostname:
            return _single_tcp_host(parsed.hostname), _valid_port(
                parsed.port or DEFAULT_DB_PORT,
                "PostgreSQL",
            )

    raise SshTransportError(
        "remote collection requires a TCP PostgreSQL endpoint in --host or a postgresql:// DSN"
    )


def tunneled_connection_kwargs(
    dsn: str | None,
    connection_kwargs: dict[str, Any],
    remote_endpoint: tuple[str, int],
    local_endpoint: tuple[str, int],
) -> dict[str, Any]:
    """Build asyncpg overrides while preserving passfile matching semantics."""
    result = dict(connection_kwargs)
    dsn_fields = _dsn_fields(dsn)
    _reject_hostname_verifying_tls(result, dsn_fields)
    password_present = result.get("password") is not None
    if not password_present and dsn_fields.get("password") is not None:
        password_present = True
    if not password_present and "PGPASSWORD" in os.environ:
        password_present = True
    passfile, passfile_required = _passfile_for_tunnel(result, dsn_fields)
    if not password_present and passfile is not None:
        user = (
            result.get("user")
            or dsn_fields.get("user")
            or os.getenv("PGUSER")
            or getpass.getuser()
        )
        database = (
            result.get("database")
            or dsn_fields.get("database")
            or os.getenv("PGDATABASE")
            or user
        )
        password = _read_pgpass_password(
            passfile,
            host=remote_endpoint[0],
            port=remote_endpoint[1],
            database=str(database),
            user=str(user),
            required_match=passfile_required,
        )
        if password is not None:
            result["password"] = password
    if password_present or passfile is not None:
        result["passfile"] = None
    result["host"] = local_endpoint[0]
    result["port"] = local_endpoint[1]
    return result


def _dsn_fields(dsn: str | None) -> dict[str, str]:
    if not dsn:
        return {}
    parsed = urlsplit(dsn)
    if parsed.scheme not in {"postgres", "postgresql"}:
        return _keyword_dsn_fields(dsn)
    query = parse_qs(parsed.query, keep_blank_values=True)

    def query_value(*names: str) -> str | None:
        for name in names:
            values = query.get(name)
            if values:
                return values[-1]
        return None

    database = unquote(parsed.path[1:]) if parsed.path.startswith("/") else unquote(parsed.path)
    values = {
        "user": unquote(parsed.username or "") or query_value("user"),
        "password": unquote(parsed.password or "") or query_value("password"),
        "database": database or query_value("database", "dbname"),
        "passfile": query_value("passfile"),
        "sslmode": query_value("sslmode"),
    }
    return {key: str(value) for key, value in values.items() if value}


def _keyword_dsn_fields(dsn: str) -> dict[str, str]:
    try:
        tokens = shlex.split(dsn)
    except ValueError:
        return {}
    values: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        normalized = "database" if key.strip().lower() == "dbname" else key.strip().lower()
        if normalized in {"user", "password", "database", "passfile", "sslmode"}:
            values[normalized] = value
    return values


def _reject_hostname_verifying_tls(
    connection_kwargs: dict[str, Any],
    dsn_fields: dict[str, str],
) -> None:
    ssl_value = connection_kwargs.get("ssl")
    ssl_mode = (
        connection_kwargs.get("sslmode")
        or dsn_fields.get("sslmode")
        or (os.getenv("PGSSLMODE") if ssl_value is None else None)
    )
    normalized_ssl_value = (
        ssl_value.strip().lower().replace("_", "-")
        if isinstance(ssl_value, str)
        else ""
    )
    hostname_verification = (
        isinstance(ssl_mode, str)
        and ssl_mode.strip().lower().replace("_", "-") == "verify-full"
    ) or ssl_value is True or (
        normalized_ssl_value == "verify-full"
    ) or (
        isinstance(ssl_value, ssl.SSLContext) and ssl_value.check_hostname
    )
    if hostname_verification:
        raise SshTransportError(
            "remote SSH tunneling cannot preserve the PostgreSQL TLS hostname required "
            "by sslmode=verify-full; use direct database connectivity when hostname "
            "verification is required"
        )
    if ssl_value is None and ssl_mode is None and os.getenv("PGSERVICE"):
        raise SshTransportError(
            "remote SSH tunneling cannot determine TLS hostname verification from "
            "PGSERVICE; pass an explicit PostgreSQL sslmode"
        )


def _passfile_for_tunnel(
    connection_kwargs: dict[str, Any],
    dsn_fields: dict[str, str],
) -> tuple[Path | None, bool]:
    explicit = connection_kwargs.get("passfile") or dsn_fields.get("passfile")
    if explicit:
        return Path(str(explicit)).expanduser(), True
    environment = os.getenv("PGPASSFILE")
    if environment:
        return Path(environment).expanduser(), True
    default = Path.home() / ".pgpass"
    if default.is_file():
        return default, False
    return None, False


def _read_pgpass_password(
    path: Path,
    *,
    host: str,
    port: int,
    database: str,
    user: str,
    required_match: bool = True,
) -> str | None:
    try:
        file_stat = path.stat()
    except OSError as exc:
        raise SshTransportError(f"cannot read PostgreSQL passfile {path}: {redact_error(exc)}") from exc
    if file_stat.st_mode & 0o077:
        raise SshTransportError(
            f"PostgreSQL passfile must not grant group or other access: {path}"
        )
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise SshTransportError(f"cannot read PostgreSQL passfile {path}: {redact_error(exc)}") from exc

    expected = (host, str(port), database, user)
    for line in lines:
        if not line or line.startswith("#"):
            continue
        fields = _split_pgpass_line(line)
        if len(fields) != 5:
            continue
        if all(pattern == "*" or pattern == value for pattern, value in zip(fields[:4], expected)):
            return fields[4]
    if required_match:
        raise SshTransportError(
            f"PostgreSQL passfile {path} has no entry for {host}:{port}:{database}:{user}"
        )
    return None


def _split_pgpass_line(line: str) -> list[str]:
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    fields.append("".join(current))
    return fields


def _single_tcp_host(value: str) -> str:
    host = value.strip()
    if not host or host.startswith("/"):
        raise SshTransportError("remote collection requires a TCP PostgreSQL host")
    if "," in host:
        raise SshTransportError("remote collection supports exactly one PostgreSQL host")
    return host


def _valid_port(value: Any, label: str) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise SshTransportError(f"{label} port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise SshTransportError(f"{label} port must be between 1 and 65535")
    return port


def _load_asyncssh() -> Any:
    try:
        import asyncssh  # type: ignore
    except ModuleNotFoundError as exc:
        raise MissingAsyncsshError(
            "asyncssh is not installed. Install pg_diag runtime dependencies before using remote mode."
        ) from exc
    return asyncssh


class SshTransport:
    """Own one SSH connection and its PostgreSQL forwarding listeners."""

    def __init__(self, config: SshConfig, connection: Any) -> None:
        self.config = config
        self._connection = connection
        self._listeners: list[Any] = []
        self._sftp: Any | None = None
        self._host_access: Any | None = None
        self._closed = False

    @classmethod
    async def connect(cls, config: SshConfig) -> SshTransport:
        config.validate()
        asyncssh = _load_asyncssh()
        try:
            connection = await asyncssh.connect(
                config.host,
                port=config.port,
                username=config.username,
                client_keys=[str(config.client_key.expanduser())],
                passphrase=config.passphrase,
                known_hosts=str(config.known_hosts.expanduser()),
                config=None,
                agent_path=None,
                preferred_auth=["publickey"],
                password_auth=False,
                kbdint_auth=False,
                host_based_auth=False,
                connect_timeout=config.connect_timeout,
                login_timeout=config.connect_timeout,
                keepalive_interval=15,
                keepalive_count_max=3,
            )
        except Exception as exc:
            raise SshTransportError(f"SSH connection failed: {redact_error(exc)}") from exc
        return cls(config, connection)

    async def open_database_tunnel(self, remote_host: str, remote_port: int) -> tuple[str, int]:
        try:
            listener = await self._connection.forward_local_port(
                "127.0.0.1",
                0,
                remote_host,
                remote_port,
            )
        except Exception as exc:
            raise SshTransportError(f"cannot open PostgreSQL SSH tunnel: {redact_error(exc)}") from exc
        self._listeners.append(listener)
        return "127.0.0.1", int(listener.get_port())

    async def run(self, command: str, *, timeout: float) -> SshCommandResult:
        result = await self._run(command, timeout=timeout, encoding="utf-8")
        return SshCommandResult(
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )

    async def run_script(
        self,
        script: str,
        *,
        arguments: tuple[str, ...] = (),
        timeout: float,
    ) -> SshCommandResult:
        """Run a local script body remotely through stdin without staging files."""
        quoted = " ".join(shlex.quote(argument) for argument in arguments)
        suffix = f" {quoted}" if quoted else ""
        wrapper = shlex.quote(REMOTE_SCRIPT_WRAPPER)
        result = await self._run(
            f"LC_ALL=C LANG=C exec /bin/sh -c {wrapper} pg-diag-script{suffix}",
            input_data=script,
            timeout=timeout,
            encoding="utf-8",
        )
        return SshCommandResult(
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )

    async def run_bytes(
        self,
        command: str,
        *,
        input_data: bytes | None = None,
        timeout: float,
    ) -> _RawCommandResult:
        """Run a command with binary streams for NUL-delimited host evidence."""
        return await self._run(
            command,
            input_data=input_data,
            timeout=timeout,
            encoding=None,
        )

    async def sftp(self) -> Any:
        """Return the SFTP client multiplexed over this SSH connection."""
        if self._sftp is None:
            try:
                self._sftp = await self._connection.start_sftp_client()
            except Exception as exc:
                raise SshTransportError(f"cannot start SFTP subsystem: {redact_error(exc)}") from exc
        return self._sftp

    @property
    def host_access(self) -> Any:
        if self._host_access is None:
            from .host_access import SshHostAccess

            self._host_access = SshHostAccess(self)
        return self._host_access

    async def _run(
        self,
        command: str,
        *,
        input_data: bytes | str | None = None,
        timeout: float,
        encoding: str | None,
    ) -> _RawCommandResult:
        try:
            process = await self._connection.create_process(
                command,
                input=input_data,
                encoding=encoding,
            )
        except Exception as exc:
            raise SshTransportError(f"cannot start remote command: {redact_error(exc)}") from exc

        budget = _OutputBudget(REMOTE_OUTPUT_LIMIT)
        stdout_task = asyncio.create_task(
            _read_bounded(process.stdout, budget, binary=encoding is None)
        )
        stderr_task = asyncio.create_task(
            _read_bounded(process.stderr, budget, binary=encoding is None)
        )
        wait_task = asyncio.create_task(process.wait_closed())
        try:
            await asyncio.wait_for(
                asyncio.gather(wait_task, stdout_task, stderr_task),
                timeout=timeout,
            )
        except asyncio.TimeoutError as exc:
            await _stop_remote_process(process)
            raise SshCommandTimeoutError(
                f"remote command timed out after {timeout:g} seconds"
            ) from exc
        except BaseException:
            await _stop_remote_process(process)
            raise
        finally:
            for task in (wait_task, stdout_task, stderr_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(wait_task, stdout_task, stderr_task, return_exceptions=True)

        return _RawCommandResult(
            returncode=int(process.returncode if process.returncode is not None else 255),
            stdout=stdout_task.result(),
            stderr=stderr_task.result(),
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for listener in self._listeners:
            try:
                listener.close()
                await listener.wait_closed()
            except Exception:
                pass
        self._listeners.clear()
        if self._sftp is not None:
            try:
                self._sftp.exit()
                await self._sftp.wait_closed()
            except Exception:
                pass
            self._sftp = None
        self._host_access = None
        try:
            self._connection.close()
            await self._connection.wait_closed()
        except Exception:
            pass


async def _read_bounded(
    stream: Any,
    budget: _OutputBudget,
    *,
    binary: bool,
) -> str | bytes:
    chunks: list[str] | list[bytes] = []
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            separator = b"" if binary else ""
            return separator.join(chunks)  # type: ignore[arg-type]
        budget.consume(chunk)
        chunks.append(chunk)


async def _stop_remote_process(process: Any) -> None:
    try:
        process.terminate()
        await asyncio.wait_for(
            process.wait_closed(),
            timeout=REMOTE_PROCESS_STOP_GRACE_SECONDS,
        )
        return
    except BaseException:
        pass
    try:
        process.kill()
        await asyncio.wait_for(
            process.wait_closed(),
            timeout=REMOTE_PROCESS_STOP_GRACE_SECONDS,
        )
        return
    except BaseException:
        pass
    try:
        process.close()
        await asyncio.wait_for(
            process.wait_closed(),
            timeout=REMOTE_PROCESS_STOP_GRACE_SECONDS,
        )
    except BaseException:
        pass
