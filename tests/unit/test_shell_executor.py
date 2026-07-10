from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from pg_diag.executors.shell import execute_shell_item
from pg_diag.planner import PlannedItem


def _planned() -> PlannedItem:
    return PlannedItem(
        item_id="os.kernel_version",
        section_id="os",
        item_key="kernel_version",
        title="Kernel And Architecture",
        source_kind="script",
        status="planned",
        source_id="os.kernel_version",
        script_file="os/test.sh",
    )


def _content(tmp_path: Path) -> SimpleNamespace:
    script = tmp_path / "scripts" / "os" / "test.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    return SimpleNamespace(
        path=tmp_path,
        report={"runtime_policy": {"default_shell_timeout_ms": 5000}},
        scripts={"os.kernel_version": {"output": "plain_text"}},
    )


def test_shell_exit_three_is_unsupported(tmp_path: Path, monkeypatch) -> None:
    content = _content(tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=3,
            stdout="",
            stderr="required utility not found\n",
        ),
    )

    item = execute_shell_item(content, _planned())

    assert item["collection_status"] == "unsupported"
    assert item["severity_level"] == "unknown"
    assert item["reason"] == "required utility not found"


def test_shell_empty_success_is_empty(tmp_path: Path, monkeypatch) -> None:
    content = _content(tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="",
            stderr="optional inventory warning",
        ),
    )

    item = execute_shell_item(content, _planned())

    assert item["collection_status"] == "empty"
    assert item["result"]["data"] == ""
    assert item["diagnostics"][0]["code"] == "shell_stderr"


def test_shell_success_stderr_is_preserved_as_warning(tmp_path: Path, monkeypatch) -> None:
    content = _content(tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="[]\n",
            stderr="WARNING: output may be incomplete\n",
        ),
    )

    item = execute_shell_item(content, _planned())

    assert item["collection_status"] == "ok"
    assert item["diagnostics"] == [
        {
            "level": "warning",
            "code": "shell_stderr",
            "message": "Shell command completed with diagnostic output",
            "stderr": "WARNING: output may be incomplete",
        }
    ]
