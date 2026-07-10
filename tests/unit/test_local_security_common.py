from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pg_diag.executors.python import _load_module


def _module(content_path: Path) -> Any:
    return _load_module(
        "test.local_security_common",
        content_path / "python" / "security" / "_local_security_common.py",
    )


def test_incomplete_coverage_is_unknown_not_pass(content_path: Path) -> None:
    module = _module(content_path)

    result = module._result(
        [],
        ok_title="complete",
        fail_title="findings",
        recommendation="inspect evidence",
        diagnostic_code="test_coverage",
        coverage_complete=False,
        coverage_note="scan limit reached",
    )

    assert result.collection_status == "ok"
    assert result.severity_level == "unknown"
    assert result.issues["summary"]["status"] == "review"
    assert "scan limit reached" in result.issues["summary"]["description"]


def test_tree_scan_reports_entry_limit(content_path: Path, tmp_path: Path) -> None:
    module = _module(content_path)
    for index in range(5):
        tmp_path.joinpath(f"file-{index}").write_text("x", encoding="utf-8")

    rows, coverage = module._world_writable_tree_findings(
        tmp_path,
        max_depth=2,
        max_rows=100,
        max_entries=2,
    )

    assert rows == []
    assert coverage["complete"] is False
    assert "entry scan limit" in coverage["reason"]


def test_plain_device_mapper_name_is_not_encryption_evidence(content_path: Path) -> None:
    module = _module(content_path)

    assert module._mount_looks_encrypted("/dev/mapper/vg-data", "ext4") is False
    assert module._source_is_confirmed_encrypted(
        "/dev/mapper/vg-data",
        "ext4",
        {"/dev/mapper/vg-data"},
    ) is True


def test_lsblk_crypt_ancestry_marks_child_sources(content_path: Path, monkeypatch) -> None:
    module = _module(content_path)
    monkeypatch.setattr(module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=(
                '{"blockdevices": [{"name": "/dev/dm-0", "path": "/dev/dm-0", '
                '"type": "crypt", "children": [{"name": "/dev/mapper/vg-data", '
                '"path": "/dev/mapper/vg-data", "type": "lvm"}]}]}'
            ),
            stderr="",
        ),
    )

    sources = module._encrypted_block_sources()

    assert "/dev/dm-0" in sources
    assert "/dev/mapper/vg-data" in sources


def test_firewall_port_matching_does_not_match_longer_port(content_path: Path) -> None:
    module = _module(content_path)
    rules = "allow tcp dport 54321 from 0.0.0.0/0 accept"

    assert module._firewall_has_broad_accept(rules, "5432") is False
    assert module._firewall_has_broad_accept(rules, "54321") is True


def test_root_owned_group_read_tls_key_is_accepted(content_path: Path) -> None:
    module = _module(content_path)

    class FakePath:
        def stat(self) -> SimpleNamespace:
            return SimpleNamespace(st_mode=0o100640, st_uid=0, st_gid=123)

        def __str__(self) -> str:
            return "/etc/ssl/private/server.key"

    assert module._tls_private_key_findings(FakePath()) == []
