from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import pg_diag.executors.shell as shell_executor
from pg_diag.errors import CommandTimeoutError
from pg_diag.executors.shell import execute_shell_item, table_json_result
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
    script.chmod(0o700)
    return SimpleNamespace(
        path=tmp_path,
        report={"runtime_policy": {"default_shell_timeout_ms": 1000}},
        scripts={"os.kernel_version": {"output": "plain_text"}},
    )


def test_shell_exit_three_is_unsupported(tmp_path: Path, monkeypatch) -> None:
    content = _content(tmp_path)
    monkeypatch.setattr(
        shell_executor,
        "run_local_process",
        lambda *args, **kwargs: shell_executor.subprocess.CompletedProcess(
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
        shell_executor,
        "run_local_process",
        lambda *args, **kwargs: shell_executor.subprocess.CompletedProcess(
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
        shell_executor,
        "run_local_process",
        lambda *args, **kwargs: shell_executor.subprocess.CompletedProcess(
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


def test_shell_timeout_is_rendered_in_the_item_result(tmp_path: Path, monkeypatch) -> None:
    content = _content(tmp_path)

    def timeout(*args, **kwargs):
        assert kwargs["timeout"] == 1.0
        raise CommandTimeoutError("local command timed out after 1 second")

    monkeypatch.setattr(shell_executor, "run_local_process", timeout)

    item = execute_shell_item(content, _planned())

    assert item["collection_status"] == "error"
    assert item["reason"] == "Shell source timed out after 1000 ms"
    assert item["result"] == {
        "kind": "plain_text",
        "data": "Shell source timed out after 1000 ms",
    }
    assert item["diagnostics"] == [
        {
            "level": "error",
            "code": "shell_timeout",
            "message": "Shell source timed out after 1000 ms",
        }
    ]


def test_shell_start_error_is_compact_and_shell_specific(tmp_path: Path, monkeypatch) -> None:
    content = _content(tmp_path)

    def fail(*args, **kwargs):
        raise OSError("cannot execute script")

    monkeypatch.setattr(shell_executor, "run_local_process", fail)

    item = execute_shell_item(content, _planned())

    assert item["collection_status"] == "error"
    assert item["result"] == {"kind": "plain_text", "data": "cannot execute script"}
    assert item["diagnostics"] == [
        {
            "level": "error",
            "code": "shell_exception",
            "message": "cannot execute script",
        }
    ]


def test_table_json_parser_does_not_apply_item_specific_normalization() -> None:
    result = table_json_result(
        """
        {"blockdevices": [{
          "name": "sda",
          "path": "/dev/sda",
          "type": "disk",
          "size": 1000,
          "model": "disk",
          "children": [{
            "name": "sda1",
            "path": "/dev/sda1",
            "pkname": "sda",
            "type": "part",
            "size": 900,
            "fstype": "ext4",
            "mountpoints": ["/var/lib/postgresql"]
          }]
        }]}
        """
    )

    columns = [column["name"] for column in result["columns"]]
    assert result["row_count"] == 1
    assert columns == ["blockdevices"]
    assert result["rows"][0][0][0]["path"] == "/dev/sda"


def test_table_json_parser_repairs_lshw_0218_filtered_output() -> None:
    result = table_json_result(
        """
        [
        {
          "id" : "host",
          "class" : "system",
          "capabilities" : {
            "smp" : "Symmetric Multi-Processing"
          }  {
            "id" : "pnp00:00",
            "class" : "system"
          },

        ]
        """,
        repair_legacy_lshw=True,
    )

    assert result["row_count"] == 2
    assert [row[0] for row in result["rows"]] == ["host", "pnp00:00"]


def test_table_json_parser_repairs_lshw_0218_empty_class() -> None:
    result = table_json_result("]", repair_legacy_lshw=True)

    assert result == {"kind": "table", "columns": [], "rows": [], "row_count": 0}


def test_table_json_parser_does_not_repair_unrelated_invalid_json() -> None:
    with pytest.raises(ValueError, match="cannot parse shell JSON output"):
        table_json_result('{"broken": }', repair_legacy_lshw=True)
