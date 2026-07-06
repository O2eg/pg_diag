from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path

import pytest

ENABLE_ENV = "PG_DIAG_DOCKER_INTEGRATION"
TRUE_VALUES = {"1", "true", "yes", "on"}


pytestmark = pytest.mark.skipif(
    os.environ.get(ENABLE_ENV, "").lower() not in TRUE_VALUES,
    reason=f"set {ENABLE_ENV}=1 to run Docker PostgreSQL integration tests",
)


def docker_available() -> bool:
    return shutil.which("docker") is not None


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run(cmd: list[str], *, timeout: int = 60, check: bool = True, **kwargs):
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


def wait_for_pg(host: str, port: int, user: str, password: str, database: str) -> None:
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    deadline = time.time() + 90
    while time.time() < deadline:
        proc = run(
            ["psql", "-h", host, "-p", str(port), "-U", user, "-d", database, "-c", "select 1"],
            timeout=10,
            check=False,
            env=env,
        )
        if proc.returncode == 0:
            return
        time.sleep(1)
    raise AssertionError(f"PostgreSQL did not become ready\nlast stderr:\n{proc.stderr}")


@pytest.mark.skipif(not docker_available(), reason="docker CLI is not installed")
def test_pgbench_loaded_database_snapshot(repo_root: Path, tmp_path: Path) -> None:
    image = os.environ.get("PG_DIAG_DOCKER_IMAGE", "postgres:18")
    container_name = f"pg-diag-it-{uuid.uuid4().hex[:12]}"
    port = free_port()
    password = "pg_diag_pw"
    user = "postgres"
    database = "postgres"
    env = os.environ.copy()
    env["PGPASSWORD"] = password

    run(
        [
            "docker",
            "run",
            "--name",
            container_name,
            "-e",
            f"POSTGRES_PASSWORD={password}",
            "-p",
            f"127.0.0.1:{port}:5432",
            "-d",
            image,
        ],
        timeout=120,
    )
    try:
        wait_for_pg("127.0.0.1", port, user, password, database)
        run(["pgbench", "-h", "127.0.0.1", "-p", str(port), "-U", user, "-i", "-s", "5", database], env=env, timeout=120)
        load_proc = subprocess.Popen(
            [
                "pgbench",
                "-h",
                "127.0.0.1",
                "-p",
                str(port),
                "-U",
                user,
                "-c",
                "4",
                "-j",
                "2",
                "-T",
                "20",
                database,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        time.sleep(3)
        out_dir = tmp_path / "report"
        dsn = f"postgresql://{user}:{password}@127.0.0.1:{port}/{database}"
        proc = run(
            [
                str(repo_root / ".venv" / "bin" / "python"),
                "-m",
                "pg_diag.cli",
                "snapshot",
                "--content",
                str(repo_root / "content"),
                "--dsn",
                dsn,
                "--out",
                str(out_dir),
            ],
            timeout=120,
            check=False,
            cwd=repo_root,
        )
        load_proc.wait(timeout=30)
        assert proc.returncode == 0, proc.stderr + proc.stdout
        report_json = out_dir / "report.json"
        report_html = out_dir / "report.html"
        assert report_json.exists()
        assert report_html.exists()
        artifact = json.loads(report_json.read_text(encoding="utf-8"))
        assert artifact["runtime"]["server_version_num"] >= 140000
        assert artifact["items"]["overview.server_version"]["status"] == "ok"
        assert "overview.database_stats" in artifact["items"]
        assert artifact["items"]["os.kernel_version"]["status"] == "skipped"
    finally:
        run(["docker", "rm", "-f", container_name], timeout=60, check=False)
