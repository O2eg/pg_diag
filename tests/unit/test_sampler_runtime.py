from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from pg_diag.content_loader import load_content
from pg_diag.errors import PgDiagError
from pg_diag.host_access import HostAccess
from pg_diag.sampler_runtime import (
    collect_sampler_providers,
    sampler_output_registry,
)
from pg_diag.ssh_transport import SshCommandTimeoutError


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
        repo_root / "pg_diag" / "artifact.py",
        repo_root / "pg_diag" / "metric_engine.py",
        repo_root / "pg_diag" / "runtime_config.py",
        repo_root / "pg_diag" / "sampler_runtime.py",
        repo_root / "pg_diag" / "snapshots.py",
        repo_root / "pg_diag" / "validator.py",
        repo_root / "pg_diag" / "executors" / "shell.py",
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

    assert "postgres|postmaster|postgres:*)" in script
    assert "postgres*|postmaster*)" not in script
    assert 'io_data="$(cat "$proc_dir/io" 2>/dev/null)"' in script
    assert 'status_data="$(cat "$proc_dir/status" 2>/dev/null)"' in script
    assert 'done < "$proc_dir/io"' not in script
    assert 'done < "$proc_dir/status"' not in script
