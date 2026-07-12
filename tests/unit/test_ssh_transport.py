from __future__ import annotations

import asyncio
import os
from pathlib import Path
import signal
import ssl
from types import SimpleNamespace
from typing import Any

import pytest
import asyncssh

import pg_diag.collection as collection_module
from pg_diag import runtime_config
from pg_diag.content_loader import load_content
from pg_diag.executors.python import execute_python_item
from pg_diag.executors.shell import execute_remote_shell_item
from pg_diag.host_access import HostAccess, SshHostAccess
from pg_diag.planner import ExecutionPlan, PlannedItem, build_plan
from pg_diag.sampler_runtime import collect_sampler_providers
from pg_diag.snapshot import collect_snapshot
from pg_diag.ssh_transport import (
    REMOTE_SCRIPT_WRAPPER,
    SshCommandResult,
    SshCommandTimeoutError,
    SshConfig,
    SshTransport,
    SshTransportError,
    remote_database_endpoint,
    tunneled_connection_kwargs,
)


class _Completed:
    def __init__(
        self,
        returncode: int = 0,
        stdout: str | bytes = "",
        stderr: str | bytes = "",
    ) -> None:
        self.returncode = returncode
        self.exit_status = returncode
        self.stdout = stdout
        self.stderr = stderr


class _FakeListener:
    def __init__(self, port: int = 49152) -> None:
        self.port = port
        self.closed = False
        self.waited = False

    def get_port(self) -> int:
        return self.port

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        self.waited = True


class _FakeSshConnection:
    def __init__(self) -> None:
        self.forward_args: tuple[Any, ...] | None = None
        self.listener = _FakeListener()
        self.closed = False
        self.waited = False

    async def forward_local_port(self, *args: Any) -> _FakeListener:
        self.forward_args = args
        return self.listener

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        self.waited = True


def _ssh_config(tmp_path: Path) -> SshConfig:
    key = tmp_path / "id_ed25519"
    known_hosts = tmp_path / "known_hosts"
    key.write_text("private-key-placeholder", encoding="utf-8")
    key.chmod(0o600)
    known_hosts.write_text("db.example ssh-ed25519 placeholder", encoding="utf-8")
    return SshConfig(
        host="db.example",
        port=2222,
        username="diagnostics",
        client_key=key,
        known_hosts=known_hosts,
        connect_timeout=7.0,
    )


def test_remote_database_endpoint_uses_explicit_host_or_uri_dsn() -> None:
    assert remote_database_endpoint(None, {"host": "127.0.0.1", "port": 5544}) == (
        "127.0.0.1",
        5544,
    )
    assert remote_database_endpoint(
        "postgresql://app:secret@db.internal:6432/appdb",
        {},
    ) == ("db.internal", 6432)
    assert remote_database_endpoint(
        "host=db.internal port=6432 dbname=appdb user=app",
        {},
    ) == ("db.internal", 6432)

    with pytest.raises(SshTransportError, match="TCP PostgreSQL"):
        remote_database_endpoint("host=/var/run/postgresql dbname=appdb", {})
    with pytest.raises(SshTransportError, match="exactly one"):
        remote_database_endpoint(None, {"host": "db1,db2"})
    with pytest.raises(SshTransportError, match="exactly one"):
        remote_database_endpoint("postgresql://db1,db2/appdb", {})


def test_tunneled_connection_resolves_passfile_against_remote_endpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PGPASSWORD", raising=False)
    passfile = tmp_path / "pgpass"
    passfile.write_text(
        "other:*:*:*:wrong\n"
        "db.internal:6432:appdb:app:secret\\:with\\\\escapes\n",
        encoding="utf-8",
    )
    passfile.chmod(0o600)

    kwargs = tunneled_connection_kwargs(
        None,
        {
            "host": "db.internal",
            "port": 6432,
            "database": "appdb",
            "user": "app",
            "passfile": str(passfile),
        },
        ("db.internal", 6432),
        ("127.0.0.1", 49152),
    )

    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 49152
    assert kwargs["password"] == "secret:with\\escapes"
    assert kwargs["passfile"] is None


def test_tunneled_connection_rejects_insecure_passfile_permissions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PGPASSWORD", raising=False)
    passfile = tmp_path / "pgpass"
    passfile.write_text("db.internal:5432:appdb:app:secret\n", encoding="utf-8")
    passfile.chmod(0o644)

    with pytest.raises(SshTransportError, match="must not grant group or other access"):
        tunneled_connection_kwargs(
            None,
            {"database": "appdb", "user": "app", "passfile": str(passfile)},
            ("db.internal", 5432),
            ("127.0.0.1", 49152),
        )


def test_tunneled_connection_uses_pgpassfile_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    passfile = tmp_path / "pgpass"
    passfile.write_text("db.internal:6432:appdb:app:environment-secret\n", encoding="utf-8")
    passfile.chmod(0o600)
    monkeypatch.delenv("PGPASSWORD", raising=False)
    monkeypatch.setenv("PGPASSFILE", str(passfile))

    kwargs = tunneled_connection_kwargs(
        None,
        {"database": "appdb", "user": "app"},
        ("db.internal", 6432),
        ("127.0.0.1", 49152),
    )

    assert kwargs["password"] == "environment-secret"
    assert kwargs["passfile"] is None


def test_tunneled_connection_uses_default_pgpass_against_remote_endpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    passfile = home / ".pgpass"
    passfile.write_text("db.internal:6432:appdb:app:default-secret\n", encoding="utf-8")
    passfile.chmod(0o600)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("PGPASSWORD", raising=False)
    monkeypatch.delenv("PGPASSFILE", raising=False)

    kwargs = tunneled_connection_kwargs(
        None,
        {"database": "appdb", "user": "app"},
        ("db.internal", 6432),
        ("127.0.0.1", 49152),
    )

    assert kwargs["password"] == "default-secret"
    assert kwargs["passfile"] is None


@pytest.mark.parametrize(
    ("dsn", "connection_kwargs"),
    [
        ("postgresql://app@db.internal/appdb?sslmode=verify-full", {}),
        ("sslmode=verify-full dbname=appdb", {"host": "db.internal"}),
        (None, {"ssl": "verify-full"}),
        (None, {"ssl": True}),
    ],
)
def test_tunneled_connection_rejects_tls_hostname_verification(
    dsn: str | None,
    connection_kwargs: dict[str, Any],
) -> None:
    with pytest.raises(SshTransportError, match="cannot preserve.*TLS hostname"):
        tunneled_connection_kwargs(
            dsn,
            connection_kwargs,
            ("db.internal", 5432),
            ("127.0.0.1", 49152),
        )


def test_tunneled_connection_rejects_hostname_checking_ssl_context() -> None:
    context = ssl.create_default_context()
    assert context.check_hostname is True

    with pytest.raises(SshTransportError, match="cannot preserve.*TLS hostname"):
        tunneled_connection_kwargs(
            None,
            {"ssl": context},
            ("db.internal", 5432),
            ("127.0.0.1", 49152),
        )


def test_tunneled_connection_rejects_verify_full_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PGSSLMODE", "verify-full")

    with pytest.raises(SshTransportError, match="cannot preserve.*TLS hostname"):
        tunneled_connection_kwargs(
            None,
            {},
            ("db.internal", 5432),
            ("127.0.0.1", 49152),
        )


def test_ssh_command_timeout_is_not_treated_as_missing_host_path() -> None:
    assert not issubclass(SshCommandTimeoutError, OSError)

    class TimeoutHost(HostAccess):
        async def stat(self, path: str | Path, *, follow_symlinks: bool = True):
            raise SshCommandTimeoutError("remote command timed out")

    with pytest.raises(SshCommandTimeoutError, match="timed out"):
        asyncio.run(TimeoutHost().exists("/remote/path"))


def test_ssh_config_requires_key_and_known_hosts(tmp_path: Path) -> None:
    config = SshConfig(
        host="db.example",
        username="diagnostics",
        client_key=tmp_path / "missing-key",
        known_hosts=tmp_path / "missing-known-hosts",
    )

    with pytest.raises(SshTransportError, match="private key does not exist"):
        config.validate()


def test_ssh_config_rejects_private_key_visible_to_group_or_other(tmp_path: Path) -> None:
    config = _ssh_config(tmp_path)
    config.client_key.chmod(0o644)

    with pytest.raises(SshTransportError, match="private key must not grant"):
        config.validate()


def test_asyncssh_connect_is_key_only_and_does_not_load_ssh_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    connection = _FakeSshConnection()

    class FakeAsyncssh:
        @staticmethod
        async def connect(host: str, **kwargs: Any) -> Any:
            calls.append((host, kwargs))
            return connection

    monkeypatch.setattr("pg_diag.ssh_transport._load_asyncssh", lambda: FakeAsyncssh)
    config = _ssh_config(tmp_path)

    transport = asyncio.run(SshTransport.connect(config))

    assert transport.config is config
    host, options = calls[0]
    assert host == "db.example"
    assert options["client_keys"] == [str(config.client_key)]
    assert options["known_hosts"] == str(config.known_hosts)
    assert options["config"] is None
    assert options["agent_path"] is None
    assert options["preferred_auth"] == ["publickey"]
    assert options["password_auth"] is False
    assert options["kbdint_auth"] is False


def test_tunnel_uses_dynamic_loopback_port_and_closes_with_connection(tmp_path: Path) -> None:
    connection = _FakeSshConnection()
    transport = SshTransport(_ssh_config(tmp_path), connection)

    endpoint = asyncio.run(transport.open_database_tunnel("127.0.0.1", 5432))
    asyncio.run(transport.close())

    assert endpoint == ("127.0.0.1", 49152)
    assert connection.forward_args == ("127.0.0.1", 0, "127.0.0.1", 5432)
    assert connection.listener.closed is True
    assert connection.listener.waited is True
    assert connection.closed is True
    assert connection.waited is True


def test_remote_shell_uses_existing_item_contract(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "os" / "test.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    content = SimpleNamespace(
        path=tmp_path,
        report={"runtime_policy": {"default_shell_timeout_ms": 1000}},
        scripts={"os.test": {"output": "table_json"}},
    )
    planned = PlannedItem(
        item_id="os.test",
        section_id="os",
        item_key="test",
        title="Test",
        source_kind="script",
        source_id="os.test",
        status="planned",
        script_file="os/test.sh",
    )

    class FakeTransport:
        async def run_script(
            self,
            script_text: str,
            *,
            arguments: tuple[str, ...] = (),
            timeout: float,
        ) -> SshCommandResult:
            assert script_text == "#!/bin/sh\n"
            assert arguments == ()
            assert timeout == 1.0
            return SshCommandResult(0, '[{"value": 42}]\n', "")

    item = asyncio.run(execute_remote_shell_item(content, planned, FakeTransport()))

    assert item["collection_status"] == "ok"
    assert item["result"]["rows"] == [[42]]
    assert item["source_metadata"]["source_language"] == "bash"


def test_remote_shell_timeout_is_rendered_in_the_item_result(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "os" / "test.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    content = SimpleNamespace(
        path=tmp_path,
        report={"runtime_policy": {"default_shell_timeout_ms": 1000}},
        scripts={"os.test": {"output": "plain_text"}},
    )
    planned = PlannedItem(
        item_id="os.test",
        section_id="os",
        item_key="test",
        title="Test",
        source_kind="script",
        source_id="os.test",
        status="planned",
        script_file="os/test.sh",
    )

    class TimeoutTransport:
        async def run_script(
            self,
            script_text: str,
            *,
            arguments: tuple[str, ...] = (),
            timeout: float,
        ) -> SshCommandResult:
            assert script_text == "#!/bin/sh\n"
            assert arguments == ()
            assert timeout == 1.0
            raise SshCommandTimeoutError("remote command timed out after 1 second")

    item = asyncio.run(execute_remote_shell_item(content, planned, TimeoutTransport()))

    assert item["collection_status"] == "error"
    assert item["reason"] == "Shell source timed out after 1000 ms"
    assert item["result"] == {
        "kind": "plain_text",
        "data": "Shell source timed out after 1000 ms",
    }
    assert item["diagnostics"][0]["code"] == "shell_timeout"


def test_local_only_python_source_evaluates_locally_with_ssh_host_access(tmp_path: Path) -> None:
    source_dir = tmp_path / "python"
    source_dir.mkdir()
    (source_dir / "source.py").write_text(
        "async def collect(ctx):\n"
        "    host_result = await ctx.host.run(('printf', 'remote-host'))\n"
        "    database = await ctx.conn.fetchval('select current_database()')\n"
        "    return {\n"
        "        'collection_status': 'ok',\n"
        "        'result': {'kind': 'plain_text', 'data': host_result.stdout + ':' + database},\n"
        "        'severity_level': 'ok',\n"
        "    }\n",
        encoding="utf-8",
    )
    content = SimpleNamespace(
        path=tmp_path,
        pythons={
            "test.remote": {
                "python_file": "source.py",
                "function": "collect",
                "local_only": True,
                "timeout_ms": 1000,
            }
        },
        python_catalog={"python_catalog": {"defaults": {}}},
    )
    planned = PlannedItem(
        item_id="s.remote",
        section_id="s",
        item_key="remote",
        title="Remote",
        source_kind="python",
        source_id="test.remote",
        status="planned",
        python_file="source.py",
    )

    class FakeDb:
        async def fetchval(self, sql: str, *args: Any) -> str:
            assert sql == "select current_database()"
            assert not args
            return "appdb"

    class FakeTransport:
        def __init__(self) -> None:
            self.host_access = SshHostAccess(self)

        async def run(self, command: str, *, timeout: float) -> SshCommandResult:
            assert "printf remote-host" in command
            assert timeout == 1.0
            return SshCommandResult(0, "remote-host", "")

    item = asyncio.run(execute_python_item(content, FakeDb(), planned, FakeTransport()))

    assert item["collection_status"] == "ok"
    assert item["result"]["data"] == "remote-host:appdb"
    assert item["severity_level"] == "ok"


def test_remote_host_command_timeout_becomes_python_item_error(tmp_path: Path) -> None:
    source_dir = tmp_path / "python"
    source_dir.mkdir()
    (source_dir / "source.py").write_text(
        "async def collect(ctx):\n"
        "    await ctx.host.run(('slow-host-command',))\n"
        "    raise AssertionError('unreachable')\n",
        encoding="utf-8",
    )
    content = SimpleNamespace(
        path=tmp_path,
        pythons={
            "test.remote_timeout": {
                "python_file": "source.py",
                "function": "collect",
                "local_only": True,
                "timeout_ms": 1000,
            }
        },
        python_catalog={"python_catalog": {"defaults": {}}},
    )
    planned = PlannedItem(
        item_id="s.remote_timeout",
        section_id="s",
        item_key="remote_timeout",
        title="Remote timeout",
        source_kind="python",
        source_id="test.remote_timeout",
        status="planned",
        python_file="source.py",
    )

    class TimeoutTransport:
        def __init__(self) -> None:
            self.host_access = SshHostAccess(self)

        async def run(self, command: str, *, timeout: float) -> SshCommandResult:
            assert "slow-host-command" in command
            assert timeout == 1.0
            raise SshCommandTimeoutError("remote command timed out after 1 second")

    item = asyncio.run(
        execute_python_item(content, SimpleNamespace(), planned, TimeoutTransport())
    )

    assert item["collection_status"] == "error"
    assert item["reason"] == "Python source timed out after 1000 ms"
    assert item["result"] == {"kind": "none"}
    assert item["diagnostics"][0]["code"] == "python_timeout"


def test_remote_plan_collects_host_scripts_python_and_samplers(content_path: Path) -> None:
    content = load_content(content_path)
    plan = build_plan(
        content,
        180000,
        mode=runtime_config.SNAPSHOTS_MODE,
        collection_mode=runtime_config.REMOTE_COLLECTION_MODE,
    )
    items = {item.item_id: item for item in plan.items}

    assert items["os.kernel_version"].status == "planned"
    assert items["cluster_inventory.pgdata_permissions"].status == "planned"
    assert items["snapshot_charts_os.os_cpu_utilization"].status == "planned"


def test_remote_collection_tunnels_dsn_and_closes_ssh_after_db(
    content_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    sql_connect_kwargs: dict[str, Any] = {}
    config = _ssh_config(tmp_path)

    class FakeDb:
        async def close(self) -> None:
            calls.append("db.close")

    class FakeTransport:
        def __init__(self) -> None:
            self.config = config
            self.peer_ip = "192.0.2.20"
            self.host_access = SimpleNamespace(hostname=self._hostname)

        async def _hostname(self) -> str:
            return "db-primary.example"

        async def open_database_tunnel(self, host: str, port: int) -> tuple[str, int]:
            assert (host, port) == ("db.internal", 6432)
            calls.append("ssh.tunnel")
            return "127.0.0.1", 49152

        async def close(self) -> None:
            calls.append("ssh.close")

    transport = FakeTransport()

    async def ssh_connect_stub(received: SshConfig) -> FakeTransport:
        assert received is config
        calls.append("ssh.connect")
        return transport

    async def sql_connect_stub(*, dsn: str | None, **kwargs: Any) -> FakeDb:
        assert dsn == "postgresql://app:secret@db.internal:6432/appdb"
        sql_connect_kwargs.update(kwargs)
        calls.append("db.connect")
        return FakeDb()

    async def runtime_stub(conn: Any) -> dict[str, Any]:
        return {
            "server_version_num": 180000,
            "server_version": "PostgreSQL 18",
            "current_database": "appdb",
            "current_user": "app",
            "in_recovery": False,
            "capabilities": {},
        }

    plan = ExecutionPlan(
        mode=runtime_config.SNAPSHOT_MODE,
        collection_mode=runtime_config.REMOTE_COLLECTION_MODE,
        server_version_num=180000,
        supported_server_version=True,
        reason=None,
        sections=[],
        items=[],
        source_jobs=[],
    )
    monkeypatch.setattr(
        collection_module.SshTransport,
        "connect",
        staticmethod(ssh_connect_stub),
    )
    monkeypatch.setattr(collection_module, "connect", sql_connect_stub)
    monkeypatch.setattr(collection_module, "detect_runtime_context", runtime_stub)
    monkeypatch.setattr(collection_module, "build_plan", lambda *args, **kwargs: plan)
    monkeypatch.setattr(collection_module, "render_html", lambda artifact, **kwargs: "<html></html>")

    artifact = asyncio.run(
        collect_snapshot(
            content=load_content(content_path),
            out_dir=tmp_path / "report",
            dsn="postgresql://app:secret@db.internal:6432/appdb",
            connection_kwargs={},
            collection_mode=runtime_config.REMOTE_COLLECTION_MODE,
            content_validated=True,
            ssh_config=config,
        )
    )

    assert sql_connect_kwargs["host"] == "127.0.0.1"
    assert sql_connect_kwargs["port"] == 49152
    assert artifact["runtime"]["remote_host"] == "db.example"
    assert artifact["runtime"]["remote_database_host"] == "db.internal"
    assert artifact["runtime"]["database_host_ip"] == "192.0.2.20"
    assert artifact["runtime"]["database_hostname"] == "db-primary.example"
    assert artifact["runtime"]["database_name"] == "appdb"
    assert artifact["runtime"]["database_role"] == "Primary"
    assert calls == [
        "ssh.connect",
        "ssh.tunnel",
        "db.connect",
        "db.close",
        "ssh.close",
    ]


class _LoopbackSshServer(asyncssh.SSHServer):
    def begin_auth(self, username: str) -> bool:
        return True

    def public_key_auth_supported(self) -> bool:
        return True

    def validate_public_key(self, username: str, key: Any) -> bool:
        return True

    def connection_requested(
        self,
        dest_host: str,
        dest_port: int,
        orig_host: str,
        orig_port: int,
    ) -> bool:
        return True


async def _copy_stream(reader: Any, writer: Any) -> None:
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            if hasattr(writer, "drain"):
                await writer.drain()
    except (BrokenPipeError, ConnectionResetError):
        pass
    finally:
        if hasattr(writer, "write_eof"):
            try:
                writer.write_eof()
            except Exception:
                pass


async def _copy_ssh_input(reader: Any, writer: Any, child: Any) -> None:
    try:
        await _copy_stream(reader, writer)
    except asyncssh.SignalReceived:
        if child.returncode is None:
            child.terminate()


async def _loopback_process_factory(process: Any) -> None:
    child = await asyncio.create_subprocess_shell(
        process.command or "",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdin_task = asyncio.create_task(_copy_ssh_input(process.stdin, child.stdin, child))
    output_tasks = [
        asyncio.create_task(_copy_stream(child.stdout, process.stdout)),
        asyncio.create_task(_copy_stream(child.stderr, process.stderr)),
    ]
    returncode = await child.wait()
    await asyncio.gather(*output_tasks, return_exceptions=True)
    stdin_task.cancel()
    await asyncio.gather(stdin_task, return_exceptions=True)
    process.exit(returncode)


async def _echo_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    data = await reader.read(1024)
    writer.write(b"echo:" + data)
    await writer.drain()
    writer.close()
    await writer.wait_closed()


def test_remote_script_wrapper_stops_process_group(tmp_path: Path) -> None:
    async def scenario() -> None:
        child_pid_file = tmp_path / "remote-child.pid"
        script = (
            "/bin/sh -c 'trap \"\" TERM; exec >/dev/null 2>&1; "
            "printf \"%s\\n\" \"$$\" > \"$1\"; sleep 30' child \"$1\" & wait\n"
        )
        process = await asyncio.create_subprocess_exec(
            "/bin/sh",
            "-c",
            REMOTE_SCRIPT_WRAPPER,
            "pg-diag-script",
            str(child_pid_file),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert process.stdin is not None
        process.stdin.write(script.encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()
        await process.stdin.wait_closed()
        for _ in range(100):
            if child_pid_file.exists():
                break
            await asyncio.sleep(0.02)
        child_pid = int(child_pid_file.read_text(encoding="utf-8"))
        process.terminate()
        await asyncio.wait_for(process.wait(), timeout=2.0)
        for _ in range(100):
            if not _process_is_running(child_pid):
                break
            await asyncio.sleep(0.02)
        try:
            assert not _process_is_running(child_pid)
        finally:
            if _process_is_running(child_pid):
                os.kill(child_pid, signal.SIGKILL)

    asyncio.run(scenario())


def test_asyncssh_end_to_end_forward_shell_sftp_and_local_python_evaluation(
    content_path: Path,
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        commands: list[str] = []

        async def process_factory(process: Any) -> None:
            commands.append(str(process.command or ""))
            await _loopback_process_factory(process)

        server_key = asyncssh.generate_private_key("ssh-ed25519")
        client_key = asyncssh.generate_private_key("ssh-ed25519")
        client_key_path = tmp_path / "client-key"
        client_key_path.write_bytes(client_key.export_private_key())
        client_key_path.chmod(0o600)

        server = await asyncssh.create_server(
            _LoopbackSshServer,
            "127.0.0.1",
            0,
            server_host_keys=[server_key],
            process_factory=process_factory,
            sftp_factory=asyncssh.SFTPServer,
            encoding=None,
        )
        ssh_port = server.get_port()
        known_hosts = tmp_path / "known_hosts"
        known_hosts.write_bytes(
            b"[127.0.0.1]:"
            + str(ssh_port).encode("ascii")
            + b" "
            + server_key.export_public_key().strip()
            + b"\n"
        )
        echo_server = await asyncio.start_server(_echo_handler, "127.0.0.1", 0)
        echo_port = int(echo_server.sockets[0].getsockname()[1])
        pgdata = tmp_path / "pgdata"
        pgdata.mkdir(mode=0o755)
        transport: SshTransport | None = None
        try:
            transport = await SshTransport.connect(
                SshConfig(
                    host="127.0.0.1",
                    port=ssh_port,
                    username="diagnostics",
                    client_key=client_key_path,
                    known_hosts=known_hosts,
                )
            )
            assert transport.peer_ip == "127.0.0.1"
            host, port = await transport.open_database_tunnel("127.0.0.1", echo_port)
            reader, writer = await asyncio.open_connection(host, port)
            writer.write(b"tunnel")
            await writer.drain()
            assert await reader.read(1024) == b"echo:tunnel"
            writer.close()
            await writer.wait_closed()

            shell = await transport.run_script(
                "#!/bin/sh\nset -eu\nuname -a\n",
                timeout=5.0,
            )
            assert shell.returncode == 0
            assert shell.stdout.strip()

            host_access = SshHostAccess(transport)
            assert await host_access.hostname()
            pgdata_stat = await host_access.stat(pgdata)
            assert pgdata_stat.is_dir

            content = load_content(content_path)
            sampler_collection = await collect_sampler_providers(
                content,
                host_access,
                1.0,
                1.0,
                {"os.cpu", "os.memory", "os.backend_proc"},
            )
            assert sampler_collection.samples["os.memory"]
            assert sampler_collection.samples["os.cpu"]
            assert "os.backend_proc" in sampler_collection.samples
            assert sampler_collection.errors == []

            plan = build_plan(
                content,
                180000,
                collection_mode=runtime_config.REMOTE_COLLECTION_MODE,
            )

            class FakeDb:
                async def fetchval(self, sql: str, *args: Any) -> str:
                    assert "data_directory" in sql
                    assert not args
                    return str(pgdata)

            planned = {
                item.item_id: item for item in plan.items
            }["cluster_inventory.pgdata_permissions"]
            python_item = await execute_python_item(content, FakeDb(), planned, transport)
            assert python_item["severity_level"] == "high"
            assert python_item["result"]["row_count"] == 1

            hba_file = tmp_path / "pg_hba.conf"
            hba_file.write_text("local all all peer\n", encoding="utf-8")
            config_file = tmp_path / "postgresql.conf"
            config_file.write_text("shared_buffers = '128MB'\n", encoding="utf-8")

            class AllChecksDb:
                settings = {
                    "hba_file": str(hba_file),
                    "data_directory": str(pgdata),
                    "config_file": str(config_file),
                    "ident_file": str(tmp_path / "pg_ident.conf"),
                    "listen_addresses": "localhost",
                    "port": "5432",
                    "ssl": "off",
                    "unix_socket_permissions": "0770",
                    "unix_socket_directories": "",
                    "logging_collector": "off",
                    "log_directory": "log",
                    "archive_mode": "off",
                    "archive_command": "",
                    "archive_library": "",
                    "ssl_key_file": "",
                    "ssl_cert_file": "",
                    "ssl_ca_file": "",
                    "ssl_crl_file": "",
                }

                class ReadOnlyTransaction:
                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, exc_type, exc, traceback):
                        return False

                def transaction(self, *, readonly: bool):
                    assert readonly is True
                    return self.ReadOnlyTransaction()

                async def fetchrow(self, sql: str) -> dict[str, Any]:
                    assert "current_setting('data_directory')" in sql
                    return {
                        "data_directory": str(pgdata),
                        "server_version_num": 180000,
                    }

                async def fetchval(self, sql: str, *args: Any) -> str:
                    if args:
                        return self.settings.get(str(args[0]), "")
                    if "select current_user" in sql:
                        return "postgres"
                    for name, value in self.settings.items():
                        if name in sql:
                            return value
                    raise AssertionError(sql)

                async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
                    if "from pg_tablespace" in sql:
                        return []
                    if "role_membership" in sql:
                        return []
                    if "where rolsuper" in sql:
                        return [{"rolname": "postgres", "rolcanlogin": True}]
                    if "pg_catalog.pg_shadow" in sql:
                        return []
                    raise AssertionError((sql, args))

            planned_by_source = {
                item.source_id: item
                for item in plan.items
                if item.source_kind == "python" and item.status == "planned"
            }
            local_only_sources = {
                source_id
                for source_id, source in content.pythons.items()
                if source.get("local_only")
            }
            assert local_only_sources <= planned_by_source.keys()
            ordered_sources = sorted(local_only_sources)
            all_items = await asyncio.gather(
                *(
                    execute_python_item(
                        content,
                        AllChecksDb(),
                        planned_by_source[source_id],
                        transport,
                    )
                    for source_id in ordered_sources
                )
            )
            errors = [
                (source_id, item.get("reason"))
                for source_id, item in zip(ordered_sources, all_items)
                if item["collection_status"] == "error"
            ]
            assert [source_id for source_id, _reason in errors] == ["cluster.pg_controldata"]
            assert errors[0][1]

            forbidden = ("python", "tar", "mktemp", "remote_agent")
            assert not any(token in command.lower() for command in commands for token in forbidden)
        finally:
            if transport is not None:
                await transport.close()
            echo_server.close()
            await echo_server.wait_closed()
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())


def _process_is_running(pid: int) -> bool:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
    except (FileNotFoundError, ProcessLookupError):
        return False
    return len(fields) > 2 and fields[2] != "Z"
