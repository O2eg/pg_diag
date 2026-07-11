from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pg_diag.executors.python import _load_module
from pg_diag.host_access import HostStat, LocalHostAccess
from pg_diag.ssh_transport import SshCommandTimeoutError


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

    rows, coverage = asyncio.run(
        module._host_world_writable_tree_findings(
            SimpleNamespace(host=LocalHostAccess()),
            tmp_path,
            max_depth=2,
            max_rows=100,
            max_entries=2,
        )
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


def test_lsblk_crypt_ancestry_marks_child_sources(content_path: Path) -> None:
    module = _module(content_path)
    sources = module._encrypted_sources_from_lsblk(
        '{"blockdevices": [{"name": "/dev/dm-0", "path": "/dev/dm-0", '
        '"type": "crypt", "children": [{"name": "/dev/mapper/vg-data", '
        '"path": "/dev/mapper/vg-data", "type": "lvm"}]}]}'
    )

    assert sources is not None
    assert "/dev/dm-0" in sources
    assert "/dev/mapper/vg-data" in sources


def test_mount_lookup_resolves_database_host_symlink_before_matching(
    content_path: Path,
) -> None:
    module = _module(content_path)

    class FakeHost:
        async def realpath(self, path: Path) -> str:
            assert path == Path("/logical/pgdata")
            return "/encrypted/storage/pgdata"

    mounts = [
        {"source": "/dev/plain", "mount": "/logical", "fstype": "ext4", "options": "rw"},
        {
            "source": "/dev/mapper/crypt",
            "mount": "/encrypted/storage",
            "fstype": "ext4",
            "options": "rw",
        },
    ]

    mount = asyncio.run(
        module._host_mount_for_path(
            SimpleNamespace(host=FakeHost()),
            Path("/logical/pgdata"),
            mounts,
        )
    )

    assert mount == mounts[1]


def test_mount_lookup_does_not_hide_host_timeout(content_path: Path) -> None:
    module = _module(content_path)

    class TimeoutHost:
        async def realpath(self, path: Path) -> str:
            raise SshCommandTimeoutError("host command timed out")

    with pytest.raises(SshCommandTimeoutError, match="timed out"):
        asyncio.run(
            module._host_mount_for_path(
                SimpleNamespace(host=TimeoutHost()),
                Path("/logical/pgdata"),
                [],
            )
        )


def test_firewall_port_matching_does_not_match_longer_port(content_path: Path) -> None:
    module = _module(content_path)
    rules = "allow tcp dport 54321 from 0.0.0.0/0 accept"

    assert module._firewall_has_broad_accept(rules, "5432") is False
    assert module._firewall_has_broad_accept(rules, "54321") is True


def test_root_owned_group_read_tls_key_is_accepted(content_path: Path) -> None:
    module = _module(content_path)

    class FakeHost:
        async def stat(self, path: Path) -> HostStat:
            return HostStat(
                path=str(path),
                mode=0o100640,
                uid=0,
                gid=123,
                owner="root",
                group="ssl-cert",
                size=0,
                mtime=0,
            )

    assert asyncio.run(
        module._host_tls_private_key_findings(
            FakeHost(),
            Path("/etc/ssl/private/server.key"),
        )
    ) == []
