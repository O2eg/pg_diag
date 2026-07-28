from __future__ import annotations

import asyncio
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

from pg_diag.content_loader import load_content
from pg_diag.errors import PgDiagError
from pg_diag.host_access import HostAccess
from pg_diag.sampler_runtime import (
    SamplerProviderContext,
    collect_sampler_providers,
    sampler_output_registry,
)
from pg_diag.ssh_transport import SshCommandResult, SshCommandTimeoutError


def test_provider_failure_is_attached_to_every_declared_required_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = ModuleType("test_sampler_provider_failure")

    async def collect(_ctx):
        raise RuntimeError("provider failed")

    module.collect = collect  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module.__name__, module)
    content = SimpleNamespace(
        path=tmp_path,
        sampler_providers={
            "test": {
                "module": module.__name__,
                "function": "collect",
                "grace_timeout_ms": 1000,
                "config": {},
                "outputs": {"first": {}, "second": {}},
            }
        },
    )

    result = asyncio.run(
        collect_sampler_providers(
            content,
            SimpleNamespace(),
            0.01,
            0.01,
            {"first", "second"},
        )
    )

    assert result.samples == {}
    assert {error["sampler"] for error in result.errors} == {"first", "second"}
    assert all("provider failed" in error["message"] for error in result.errors)


def test_provider_warning_preserves_successful_selected_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = ModuleType("test_sampler_provider_warning")

    async def collect(_ctx):
        return {
            "samples": {
                "selected": [
                    {
                        "timestamp": "2026-07-28T00:00:00Z",
                        "rows": [{"value": 1}],
                    }
                ],
                "unselected": [],
            },
            "errors": [],
            "warnings": [
                {
                    "sampler": "selected",
                    "code": "bounded_coverage",
                    "message": "sampled 1 of 10 rows",
                },
                {
                    "sampler": "unselected",
                    "code": "not_requested",
                    "message": "must be filtered",
                },
            ],
        }

    module.collect = collect  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module.__name__, module)
    content = SimpleNamespace(
        path=tmp_path,
        sampler_providers={
            "test": {
                "module": module.__name__,
                "function": "collect",
                "grace_timeout_ms": 1000,
                "config": {},
                "outputs": {"selected": {}, "unselected": {}},
            }
        },
    )

    result = asyncio.run(
        collect_sampler_providers(
            content,
            SimpleNamespace(),
            0.01,
            0.01,
            {"selected"},
        )
    )

    assert result.errors == []
    assert result.samples["selected"][0]["rows"] == [{"value": 1}]
    assert result.warnings == [
        {
            "sampler": "selected",
            "code": "bounded_coverage",
            "message": "sampled 1 of 10 rows",
        }
    ]


def test_linux_proc_timeout_is_reported_for_each_selected_output(content_path: Path) -> None:
    class TimeoutHost(HostAccess):
        async def run_script(self, script: str, *, arguments=(), timeout: float = 1.0):
            raise SshCommandTimeoutError("host command timed out")

    content = load_content(content_path)
    selected = {"os.cpu", "os.memory", "os.network"}

    result = asyncio.run(
        collect_sampler_providers(content, TimeoutHost(), 0.01, 0.01, selected)
    )

    assert set(result.samples) == selected
    assert all(result.samples[output_id] == [] for output_id in selected)
    assert {error["sampler"] for error in result.errors} == selected
    assert all("timed out" in error["message"] for error in result.errors)


def test_sampler_registry_is_built_only_from_content_contract(content_path: Path) -> None:
    content = load_content(content_path)

    registry = sampler_output_registry(content)

    declared = {
        output_id
        for provider in content.sampler_providers.values()
        for output_id in provider["outputs"]
    }
    assert set(registry) == declared


def test_runtime_rejects_required_output_missing_from_contract(tmp_path: Path) -> None:
    content = SimpleNamespace(path=tmp_path, sampler_providers={})

    with pytest.raises(PgDiagError, match="required sampler outputs are not declared"):
        asyncio.run(
            collect_sampler_providers(
                content,
                SimpleNamespace(),
                0.01,
                0.01,
                {"missing"},
            )
        )


def test_engine_modules_do_not_embed_item_or_sampler_implementation_names(
    repo_root: Path,
) -> None:
    core_files = [
        repo_root / "src" / "pg_diag" / "artifact.py",
        repo_root / "src" / "pg_diag" / "metric_engine.py",
        repo_root / "src" / "pg_diag" / "runtime_config.py",
        repo_root / "src" / "pg_diag" / "sampler_runtime.py",
        repo_root / "src" / "pg_diag" / "snapshots.py",
        repo_root / "src" / "pg_diag" / "validator.py",
        repo_root / "src" / "pg_diag" / "executors" / "shell.py",
    ]
    forbidden = (
        "os.cpu",
        "os.memory",
        "os.disk",
        "os.network",
        "os.backend_proc",
        "datname",
        "database_name",
        "lsblk",
        "iostat",
        "/proc",
    )

    for path in core_files:
        text = path.read_text(encoding="utf-8")
        assert not any(value in text for value in forbidden), path


def test_postgresql_process_sampler_matcher_is_exact(content_path: Path) -> None:
    script = (
        content_path / "scripts" / "samplers" / "postgresql_backend_proc.sh"
    ).read_text(encoding="utf-8")

    assert '$4 == "postgres" || $4 == "postmaster" || $4 ~ /^postgres:/' in script
    assert "ps -eo pid=,stat=,pcpu=,comm=,args= --sort=-pcpu" in script
    assert "for proc_dir in /proc/[0-9]*" not in script
    assert 'cat "$proc_dir/io"' not in script
    assert 'cat "$proc_dir/status"' not in script
    assert "tr '\\000'" not in script
    assert 'done < "$proc_dir/io"' in script
    assert "substr(command, 1, 220)" in script


def test_postgresql_process_sampler_reports_ps_discovery_failure(
    content_path: Path,
    tmp_path: Path,
) -> None:
    fake_ps = tmp_path / "ps"
    fake_ps.write_text(
        "#!/bin/sh\n"
        "printf 'unsupported ps options\\n' >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    fake_ps.chmod(0o755)
    script_path = (
        content_path / "scripts" / "samplers" / "postgresql_backend_proc.sh"
    )

    completed = subprocess.run(
        ("/bin/sh", str(script_path), "discover", "2"),
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
    )

    assert completed.returncode == 4
    assert "ps backend discovery failed with exit code 2" in completed.stderr
    assert "unsupported ps options" in completed.stderr


def test_postgresql_process_sampler_accepts_vanished_selected_pids(
    content_path: Path,
    tmp_path: Path,
) -> None:
    fake_ps = tmp_path / "ps"
    fake_ps.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fake_ps.chmod(0o755)
    script_path = (
        content_path / "scripts" / "samplers" / "postgresql_backend_proc.sh"
    )

    completed = subprocess.run(
        ("/bin/sh", str(script_path), "selected", "2", "999999", "1"),
        capture_output=True,
        timeout=5,
        check=False,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
    )

    fields = completed.stdout.split(b"\0")
    assert completed.returncode == 0
    assert completed.stderr == b""
    assert fields[2:4] == [b"1", b"1"]
    assert fields[4:] == [b""]


def test_postgresql_process_sampler_limits_and_freezes_selected_pids(
    content_path: Path,
) -> None:
    def frame(
        monotonic: float,
        *,
        discovered: int,
        selected: int,
        utime: int,
        read_bytes: int,
    ) -> str:
        values = [
            "100",
            str(monotonic),
            str(discovered),
            str(selected),
        ]
        for pid in (101, 202):
            values.extend(
                [
                    str(pid),
                    "postgres",
                    f"postgres: app{pid} testdb idle",
                    "S",
                    str(pid * 10),
                    str(utime),
                    "50",
                    str(read_bytes),
                    "500",
                    "0",
                    "10",
                    "5",
                    "1",
                    "4",
                ]
            )
        return "\0".join(values) + "\0"

    class BoundedBackendHost(HostAccess):
        def __init__(self) -> None:
            self.calls: list[tuple[str, ...]] = []

        async def run_script(self, script: str, *, arguments=(), timeout: float = 1.0):
            assert script
            assert timeout == 5.0
            self.calls.append(tuple(arguments))
            if arguments[0] == "discover":
                assert arguments == ("discover", "2000")
                return SshCommandResult(
                    0,
                    frame(
                        10.0,
                        discovered=10000,
                        selected=2000,
                        utime=100,
                        read_bytes=1000,
                    ),
                    "",
                )
            assert arguments == ("selected", "2000", "101,202", "10000")
            return SshCommandResult(
                0,
                frame(
                    12.0,
                    discovered=10000,
                    selected=2,
                    utime=120,
                    read_bytes=2000,
                ),
                "",
            )

    content = load_content(content_path)
    context = SamplerProviderContext(
        content_path=content.path,
        host=BoundedBackendHost(),
        duration_seconds=0.001,
        interval_seconds=0.001,
        required_outputs=frozenset({"os.backend_proc"}),
        manifest=content.sampler_providers["postgresql_backend_proc"],
    )

    from pg_diag.providers.linux import collect_postgresql_backend_proc

    result = asyncio.run(collect_postgresql_backend_proc(context))

    assert result.errors == []
    assert result.samples["os.backend_proc"][0]["rows"]
    warnings = {warning["code"]: warning["message"] for warning in result.warnings}
    assert "2 of 10000 processes" in warnings["backend_process_limit"]
    assert (
        "start: selected=2000, captured=2"
        in warnings["backend_process_capture_incomplete"]
    )
    assert context.host.calls == [
        ("discover", "2000"),
        ("selected", "2000", "101,202", "10000"),
    ]


def test_postgresql_process_sampler_has_bounded_manifest(content_path: Path) -> None:
    provider = load_content(content_path).sampler_providers["postgresql_backend_proc"]

    assert provider["grace_timeout_ms"] == 7000
    assert provider["config"]["max_processes"] == 2000
