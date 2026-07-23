from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace

import pytest

from pg_diag import cli, configuration_facts
from pg_diag.configuration_facts import (
    CONFIGURATION_ITEM_IDS,
    extract_configuration_facts,
    validate_configuration_facts,
)
from pg_diag.errors import ValidationError
from pg_diag.orchestration import capabilities


def _table(rows: list[dict[str, object]]) -> dict[str, object]:
    names = list(rows[0]) if rows else []
    return {
        "collection_status": "ok" if rows else "empty",
        "result": {
            "kind": "table",
            "columns": [{"name": name} for name in names],
            "rows": [[row.get(name) for name in names] for row in rows],
        },
    }


def _plain(value: str) -> dict[str, object]:
    return {"collection_status": "ok", "result": {"kind": "plain_text", "data": value}}


def _artifact() -> dict[str, object]:
    items = {item_id: _table([]) for item_id in CONFIGURATION_ITEM_IDS}
    items.update(
        {
            "overview.server_version": _table(
                [{"version": "PostgreSQL 18.1 on x86_64-pc-linux-gnu"}]
            ),
            "overview.pg_settings": _table(
                [
                    {
                        "setting_name": "shared_buffers",
                        "setting_value": "16384",
                        "setting_normalized": "134217728",
                        "unit_normalized": "bytes",
                        "quantity_normalized": "data_volume",
                        "source_unit": "8kB",
                        "source": "configuration file",
                        "context": "postmaster",
                        "pending_restart": False,
                        "boot_val": "16384",
                        "reset_val": "16384",
                        "is_default": False,
                    }
                ]
            ),
            "overview.database_volume": _table(
                [
                    {"database_name": "app", "database_size_bytes": 1000},
                    {"database_name": "postgres", "database_size_bytes": 200},
                ]
            ),
            "os.total_ram": _table([{"total_ram_bytes": 17179869184}]),
            "os.cpu_info": _plain(
                "Architecture: x86_64\nCPU(s): 8\nSocket(s): 1\n"
                "Core(s) per socket: 4\nThread(s) per core: 2\nModel name: Test CPU\n"
            ),
            "os.disk_usage": _table(
                [{"filesystem": "/dev/sda", "total_bytes": 10000, "mount_point": "/"}]
            ),
            "os.mounts": _plain("/dev/sda on / type ext4 (rw)"),
            "os.lshw_disk": _table([{"product": "Test NVMe"}]),
            "cluster_inventory.extensions": _table(
                [
                    {"name": "pg_stat_statements", "installed": True},
                    {"name": "postgis", "installed": False},
                ]
            ),
        }
    )
    return {
        "artifact_schema_version": 4,
        "generator": {"name": "pg_diag", "version": "test"},
        "runtime": {
            "server_version_num": 180001,
            "started_at": "2026-07-23T00:00:00Z",
        },
        "items": items,
    }


def test_extract_configuration_facts_normalizes_tuning_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(configuration_facts, "validate_artifact", lambda _artifact: None)

    facts = extract_configuration_facts(_artifact(), source_path="report.json")

    assert facts["schema_version"] == "pg_diag/configuration-facts-v1"
    assert facts["postgresql"]["major"] == "18"
    assert facts["postgresql"]["database_size_bytes"] == 1200
    assert facts["postgresql"]["installed_extensions"] == ["pg_stat_statements"]
    assert facts["postgresql"]["available_extensions"] == ["pg_stat_statements", "postgis"]
    assert facts["host"]["cpu_cores"] == 8
    assert facts["host"]["ram_bytes"] == 17179869184
    assert facts["postgresql"]["settings"]["shared_buffers"]["normalized_value"] == 134217728
    assert facts["collection"]["usable"] is True
    validate_configuration_facts(facts)

    facts["host"]["ram_bytes"] = 1
    with pytest.raises(ValidationError, match="hash does not match"):
        validate_configuration_facts(facts)


def test_missing_critical_item_marks_facts_unusable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(configuration_facts, "validate_artifact", lambda _artifact: None)
    artifact = _artifact()
    del artifact["items"]["os.total_ram"]

    facts = extract_configuration_facts(artifact)

    assert facts["collection"]["usable"] is False
    assert facts["collection"]["missing_item_ids"] == ["os.total_ram"]


def test_empty_critical_result_marks_facts_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(configuration_facts, "validate_artifact", lambda _artifact: None)
    artifact = _artifact()
    artifact["items"]["overview.pg_settings"] = _table([])

    facts = extract_configuration_facts(artifact)

    assert facts["collection"]["usable"] is False
    assert facts["collection"]["invalid_item_ids"] == ["overview.pg_settings"]


def test_configuration_facts_schema_and_capability_are_packaged() -> None:
    schema_path = files("pg_diag").joinpath("schema/configuration-facts-v1.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert schema["properties"]["schema_version"]["const"] == "pg_diag/configuration-facts-v1"
    assert "configuration-facts" in capabilities()["commands"]


def test_configuration_facts_cli_writes_private_atomic_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    expected = {"schema_version": "pg_diag/configuration-facts-v1", "facts_hash": "sha256:x"}
    destination = tmp_path / "facts" / "configuration.json"
    monkeypatch.setattr(cli, "load_artifact", lambda _path: {"report": True})
    monkeypatch.setattr(
        cli,
        "extract_configuration_facts",
        lambda _artifact, source_path: expected,
    )

    result = cli.cmd_configuration_facts(
        SimpleNamespace(artifact="report.json", out=str(destination))
    )

    assert result == 0
    assert json.loads(destination.read_text(encoding="utf-8")) == expected
    assert destination.stat().st_mode & 0o777 == 0o600
    assert json.loads(capsys.readouterr().out) == expected
