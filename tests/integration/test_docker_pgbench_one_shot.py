from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import uuid

import asyncssh
import pytest

from pg_diag.content_loader import load_content
from pg_diag.planner import build_plan
from pg_diag.runtime_config import ONE_SHOT_MODE, REMOTE_COLLECTION_MODE, SNAPSHOTS_MODE


ENABLE_ENV = "PG_DIAG_DOCKER_INTEGRATION"
VERSIONS_ENV = "PG_DIAG_DOCKER_VERSIONS"
TRUE_VALUES = {"1", "true", "yes", "on"}
SUPPORTED_MAJORS = (10, 11, 12, 13, 14, 15, 16, 17, 18)
REPO_ROOT = Path(__file__).resolve().parents[2]
CONTENT_PATH = REPO_ROOT / "src" / "pg_diag" / "content"
DOCKER_CONTEXT = Path(__file__).resolve().parent / "docker"


def docker_available() -> bool:
    return shutil.which("docker") is not None


def configured_postgres_majors() -> tuple[int, ...]:
    raw = os.environ.get(VERSIONS_ENV, ",".join(str(version) for version in SUPPORTED_MAJORS))
    try:
        majors = tuple(int(entry.strip()) for entry in raw.split(",") if entry.strip())
    except ValueError as exc:
        raise ValueError(f"{VERSIONS_ENV} must contain comma-separated PostgreSQL majors") from exc
    if not majors:
        raise ValueError(f"{VERSIONS_ENV} must select at least one PostgreSQL major")
    unsupported = sorted(set(majors).difference(SUPPORTED_MAJORS))
    if unsupported:
        raise ValueError(
            f"{VERSIONS_ENV} supports only PostgreSQL 10-18; unknown: "
            + ", ".join(str(version) for version in unsupported)
        )
    if len(set(majors)) != len(majors):
        raise ValueError(f"{VERSIONS_ENV} contains a duplicate PostgreSQL major")
    return majors


POSTGRES_MAJORS = configured_postgres_majors()

pytestmark = [
    pytest.mark.skipif(
        os.environ.get(ENABLE_ENV, "").lower() not in TRUE_VALUES,
        reason=f"set {ENABLE_ENV}=1 to run Docker PostgreSQL integration tests",
    ),
    pytest.mark.skipif(not docker_available(), reason="docker CLI is not installed"),
]


@dataclass(frozen=True)
class PreparedPostgres:
    major: int
    container_name: str
    host: str
    user: str
    password: str
    database: str
    ssh_user: str
    ssh_key: Path
    ssh_known_hosts: Path


def run(
    cmd: list[str],
    *,
    timeout: int = 60,
    check: bool = True,
    **kwargs: object,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        **kwargs,
    )
    if check and proc.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(cmd)}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


def wait_for_postgres(container_name: str) -> None:
    deadline = time.time() + 90
    last_stderr = ""
    while time.time() < deadline:
        proc = run(
            [
                "docker",
                "exec",
                container_name,
                "pg_isready",
                "-U",
                "postgres",
                "-d",
                "postgres",
            ],
            timeout=10,
            check=False,
        )
        if proc.returncode == 0:
            return
        last_stderr = proc.stderr
        time.sleep(1)
    raise AssertionError(f"PostgreSQL did not become ready\nlast stderr:\n{last_stderr}")


def wait_for_tcp(host: str, port: int) -> None:
    deadline = time.time() + 30
    last_error: OSError | None = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.25)
    raise AssertionError(f"TCP endpoint {host}:{port} did not become ready: {last_error}")


def build_integration_image(major: int) -> str:
    image_tag = f"{major}-bullseye" if major == 10 else f"{major}-bookworm"
    dockerfile = DOCKER_CONTEXT / "Dockerfile"
    digest = sha256()
    digest.update(dockerfile.read_bytes())
    digest.update(b"\0")
    digest.update(str(major).encode("ascii"))
    digest.update(b"\0")
    digest.update(image_tag.encode("ascii"))
    image = f"pg-diag-integration-pg{major}:sha-{digest.hexdigest()[:16]}"
    force_build = os.environ.get("PG_DIAG_DOCKER_PULL", "").lower() in TRUE_VALUES
    if not force_build:
        inspected = run(["docker", "image", "inspect", image], check=False)
        if inspected.returncode == 0:
            return image
    command = [
        "docker",
        "build",
        "--build-arg",
        f"PG_MAJOR={major}",
        "--build-arg",
        f"PG_IMAGE_TAG={image_tag}",
        "--tag",
        image,
        str(DOCKER_CONTEXT),
    ]
    if force_build:
        command.insert(2, "--pull")
    run(command, timeout=900)
    return image


def container_ip(container_name: str) -> str:
    proc = run(
        [
            "docker",
            "inspect",
            "--format",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            container_name,
        ]
    )
    address = proc.stdout.strip()
    if not address:
        raise AssertionError(f"Docker did not assign an IPv4 address to {container_name}")
    return address


def psql(container_name: str, sql: str) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "docker",
            "exec",
            container_name,
            "psql",
            "--set",
            "ON_ERROR_STOP=1",
            "--tuples-only",
            "--no-align",
            "--username",
            "postgres",
            "--dbname",
            "postgres",
            "--command",
            sql,
        ],
        timeout=60,
    )


def assert_legacy_host_tool_versions(cluster: PreparedPostgres) -> None:
    if cluster.major != 10:
        return
    versions = run(
        [
            "docker",
            "exec",
            cluster.container_name,
            "dpkg-query",
            "--show",
            "--showformat=${Package}=${Version}\\n",
            "lshw",
            "sysstat",
        ]
    ).stdout.splitlines()
    assert any(entry.startswith("lshw=02.18.") for entry in versions), versions
    assert any(entry.startswith("sysstat=12.5.") for entry in versions), versions


def prepare_postgres_extensions(container_name: str) -> None:
    preloads = {
        entry.strip()
        for entry in psql(container_name, "show shared_preload_libraries").stdout.split(",")
        if entry.strip()
    }
    assert {"pg_stat_statements", "pg_wait_sampling"} <= preloads

    for extension in ("pg_stat_statements", "pg_wait_sampling", "pg_buffercache"):
        psql(container_name, f"create extension if not exists {extension}")

    installed = {
        line.strip()
        for line in psql(
            container_name,
            "select extname from pg_extension order by extname",
        ).stdout.splitlines()
        if line.strip()
    }
    assert {"pg_stat_statements", "pg_wait_sampling", "pg_buffercache"} <= installed


def prepare_ssh(
    container_name: str,
    host: str,
    ssh_directory: Path,
) -> tuple[Path, Path]:
    client_key = asyncssh.generate_private_key("ssh-ed25519")
    private_key = ssh_directory / "id_ed25519"
    private_key.write_bytes(client_key.export_private_key())
    private_key.chmod(0o600)
    public_key = client_key.export_public_key().decode("utf-8").strip() + "\n"

    run(["docker", "exec", container_name, "install", "-d", "-m", "0700", "/root/.ssh"])
    run(
        ["docker", "exec", "--interactive", container_name, "tee", "/root/.ssh/authorized_keys"],
        input=public_key,
    )
    run(
        [
            "docker",
            "exec",
            container_name,
            "chmod",
            "0600",
            "/root/.ssh/authorized_keys",
        ]
    )
    run(["docker", "exec", container_name, "ssh-keygen", "-A"])
    run(["docker", "exec", container_name, "/usr/sbin/sshd", "-t"])
    run(["docker", "exec", container_name, "/usr/sbin/sshd"])

    host_key = run(
        [
            "docker",
            "exec",
            container_name,
            "cat",
            "/etc/ssh/ssh_host_ed25519_key.pub",
        ]
    ).stdout.split()
    assert len(host_key) >= 2
    known_hosts = ssh_directory / "known_hosts"
    known_hosts.write_text(f"{host} {host_key[0]} {host_key[1]}\n", encoding="utf-8")
    known_hosts.chmod(0o600)
    wait_for_tcp(host, 22)
    return private_key, known_hosts


@pytest.fixture(scope="module", params=POSTGRES_MAJORS, ids=lambda major: f"pg{major}")
def prepared_postgres(
    request: pytest.FixtureRequest,
    tmp_path_factory: pytest.TempPathFactory,
) -> PreparedPostgres:
    major = int(request.param)
    image = build_integration_image(major)
    container_name = f"pg-diag-it-pg{major}-{uuid.uuid4().hex[:10]}"
    password = "pg_diag_pw"

    postgres_options = [
        "docker",
        "run",
        "--name",
        container_name,
        "--init",
        "--shm-size",
        "256m",
        "--cap-add",
        "SYS_PTRACE",
        "--env",
        f"POSTGRES_PASSWORD={password}",
        "--detach",
        image,
        "postgres",
        "-c",
        "shared_preload_libraries=pg_stat_statements,pg_wait_sampling",
        "-c",
        "pg_stat_statements.track=all",
        "-c",
        "track_io_timing=on",
    ]
    if major >= 14:
        postgres_options.extend(["-c", "compute_query_id=on"])
    run(postgres_options, timeout=120)
    try:
        wait_for_postgres(container_name)
        prepare_postgres_extensions(container_name)
        run(
            [
                "docker",
                "exec",
                container_name,
                "pgbench",
                "--username",
                "postgres",
                "--initialize",
                "--scale",
                "1",
                "postgres",
            ],
            timeout=120,
        )
        host = container_ip(container_name)
        ssh_directory = tmp_path_factory.mktemp(f"pg{major}-ssh")
        ssh_key, known_hosts = prepare_ssh(container_name, host, ssh_directory)
        yield PreparedPostgres(
            major=major,
            container_name=container_name,
            host=host,
            user="postgres",
            password=password,
            database="postgres",
            ssh_user="root",
            ssh_key=ssh_key,
            ssh_known_hosts=known_hosts,
        )
    finally:
        run(["docker", "rm", "--force", container_name], timeout=60, check=False)


def start_pgbench_load(cluster: PreparedPostgres) -> None:
    run(
        [
            "docker",
            "exec",
            "--detach",
            cluster.container_name,
            "pgbench",
            "--username",
            cluster.user,
            "--client",
            "2",
            "--jobs",
            "2",
            "--time",
            "180",
            cluster.database,
        ]
    )
    time.sleep(1)


def stop_pgbench_load(cluster: PreparedPostgres) -> None:
    run(
        ["docker", "exec", cluster.container_name, "pkill", "-TERM", "-x", "pgbench"],
        check=False,
    )


def report_error_summary(report_path: Path) -> str:
    if not report_path.is_file():
        return "report.json was not written"
    artifact = json.loads(report_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for item_id, item in (artifact.get("items") or {}).items():
        if item.get("collection_status") == "error":
            errors.append(f"{item_id}: {item.get('reason')}")
    for index, snapshot in enumerate(artifact.get("snapshots") or []):
        for item_id, item in (snapshot.get("items") or {}).items():
            if item.get("collection_status") == "error":
                errors.append(f"snapshot[{index}] {item_id}: {item.get('reason')}")
    return "\n".join(errors) if errors else "no item errors found in written report"


def collect_report(
    cluster: PreparedPostgres,
    mode: str,
    out_dir: Path,
) -> tuple[dict[str, object], str]:
    command = [
        sys.executable,
        str(Path(__file__).resolve().parent / "_run_pg_diag.py"),
        mode,
        "--content",
        str(CONTENT_PATH),
        "--host",
        "127.0.0.1",
        "--port",
        "5432",
        "--database",
        cluster.database,
        "--user",
        cluster.user,
        "--password",
        cluster.password,
        "--collection-mode",
        REMOTE_COLLECTION_MODE,
        "--ssh-host",
        cluster.host,
        "--ssh-user",
        cluster.ssh_user,
        "--ssh-key",
        str(cluster.ssh_key),
        "--ssh-known-hosts",
        str(cluster.ssh_known_hosts),
        "--out",
        str(out_dir),
    ]
    if mode == SNAPSHOTS_MODE:
        command.extend(
            [
                "--duration-seconds",
                "5",
                "--interval-seconds",
                "5",
            ]
        )

    start_pgbench_load(cluster)
    try:
        proc = run(command, timeout=480, check=False, cwd=REPO_ROOT)
    finally:
        stop_pgbench_load(cluster)

    report_path = out_dir / "report.json"
    assert proc.returncode == 0, (
        f"PostgreSQL {cluster.major} {mode} failed\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}\n"
        f"item errors:\n{report_error_summary(report_path)}"
    )
    assert report_path.is_file()
    assert (out_dir / "report.html").is_file()
    report_log = out_dir / "report.log"
    assert report_log.is_file()
    return (
        json.loads(report_path.read_text(encoding="utf-8")),
        report_log.read_text(encoding="utf-8"),
    )


def assert_no_collection_errors(artifact: dict[str, object]) -> None:
    errors: list[tuple[str, object]] = []
    for item_id, item in (artifact.get("items") or {}).items():
        if item.get("collection_status") == "error":
            errors.append((item_id, item.get("reason")))
    for index, snapshot in enumerate(artifact.get("snapshots") or []):
        for item_id, item in (snapshot.get("items") or {}).items():
            if item.get("collection_status") == "error":
                errors.append((f"snapshot[{index}] {item_id}", item.get("reason")))
    assert errors == []


def assert_no_sampler_errors(artifact: dict[str, object]) -> None:
    errors = [
        diagnostic
        for diagnostic in artifact.get("diagnostics") or []
        if diagnostic.get("code") == "sampler_provider"
    ]
    assert errors == []


def assert_remote_host_items_ran(
    artifact: dict[str, object],
    report_log: str,
    mode: str,
) -> None:
    server_version_num = int(artifact["runtime"]["server_version_num"])
    content = load_content(CONTENT_PATH)
    plan = build_plan(
        content,
        server_version_num,
        mode=mode,
        collection_mode=REMOTE_COLLECTION_MODE,
    )
    expected = {
        item.item_id
        for item in plan.items
        if item.status == "planned" and item.source_kind in {"script", "python"}
    }
    actual = artifact.get("items") or {}
    missing = sorted(
        item_id
        for item_id in expected.difference(actual)
        if f"SKIP item={item_id} " not in report_log
        and f"ITEM item={item_id} " not in report_log
    )
    assert missing == []
    not_executed = sorted(
        item_id
        for item_id in expected.intersection(actual)
        if actual[item_id].get("collection_status") in {"error", "skipped"}
    )
    assert not_executed == []


def assert_items_ran(artifact: dict[str, object], item_ids: set[str]) -> None:
    items = artifact.get("items") or {}
    missing = sorted(item_ids.difference(items))
    assert missing == []
    failed = sorted(
        item_id
        for item_id in item_ids
        if items[item_id].get("collection_status") in {"error", "skipped", "unsupported"}
    )
    assert failed == []


def test_remote_one_shot_runs_all_applicable_items(
    prepared_postgres: PreparedPostgres,
    tmp_path: Path,
) -> None:
    assert_legacy_host_tool_versions(prepared_postgres)
    artifact, report_log = collect_report(
        prepared_postgres,
        ONE_SHOT_MODE,
        tmp_path / f"pg{prepared_postgres.major}-one-shot-remote",
    )

    assert int(artifact["runtime"]["server_version_num"]) // 10000 == prepared_postgres.major
    assert_no_collection_errors(artifact)
    assert_remote_host_items_ran(artifact, report_log, ONE_SHOT_MODE)
    required_items = {
        "activity_locks.pg_wait_sampling_capabilities",
        "activity_locks.pg_wait_sampling_profile",
        "sql_workload.pg_stat_statements_capabilities",
        "sql_workload.top_sql_by_total_time",
        "sql_workload.top_sql_by_mean_time",
        "sql_workload.top_sql_by_calls",
        "sql_workload.top_sql_by_shared_io",
        "sql_workload.top_sql_by_temp_io",
    }
    if prepared_postgres.major >= 13:
        required_items.add("sql_workload.top_sql_by_wal")
    assert_items_ran(artifact, required_items)


def test_remote_snapshots_runs_all_items_and_collection_scopes(
    prepared_postgres: PreparedPostgres,
    tmp_path: Path,
) -> None:
    artifact, report_log = collect_report(
        prepared_postgres,
        SNAPSHOTS_MODE,
        tmp_path / f"pg{prepared_postgres.major}-snapshots-remote",
    )

    assert int(artifact["runtime"]["server_version_num"]) // 10000 == prepared_postgres.major
    assert len(artifact["snapshots"]) == 2
    assert_no_collection_errors(artifact)
    assert_no_sampler_errors(artifact)
    assert_remote_host_items_ran(artifact, report_log, SNAPSHOTS_MODE)
    required_items = {
        "activity_locks.wait_event_sample_profile",
        "activity_locks.pg_wait_sampling_capabilities",
        "activity_locks.pg_wait_sampling_profile",
        "snapshot_charts_os.os_disk_read_throughput",
        "snapshot_charts_os.os_disk_write_throughput",
        "snapshot_charts_os.os_disk_iops",
        "snapshot_charts_os.os_disk_utilization",
        "snapshot_charts_os.os_disk_latency",
        "sql_workload.pg_stat_statements_capabilities",
        "snapshot_delta_workload.sql_time_delta",
        "snapshot_delta_workload.sql_io_delta",
        "snapshot_delta_workload.sql_temp_io_delta",
    }
    if prepared_postgres.major >= 13:
        required_items.update(
            {
                "snapshot_delta_workload.sql_wal_delta",
                "snapshot_delta_workload.sql_planning_delta",
            }
        )
    assert_items_ran(artifact, required_items)
