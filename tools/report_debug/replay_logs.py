"""Compare local and shell log scanners on saved CSV logs without a DB connection."""

import argparse
import asyncio
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

from pg_diag.logscan.harvester import BashHarvesterSource
from pg_diag.logscan.item_recall import clauses_for_items
from pg_diag.logscan.model import AUTO_EXPLAIN_RAW_RECORD_CAP, LogFileInfo, ScanRequest
from pg_diag.logscan.phase import _build_window
from pg_diag.logscan.sources import LocalLogSource

from common import read_artifact, write_json

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("report", type=Path, help="Supplies selected server_log items and PG version")
parser.add_argument("logs", type=Path, nargs="+", help="CSV files in the same directory")
parser.add_argument(
    "--from", dest="start", required=True, help="Server log time YYYY-MM-DD HH:MM:SS"
)
parser.add_argument("--to", dest="end", required=True, help="Server log time YYYY-MM-DD HH:MM:SS")
parser.add_argument("--timeout", type=float, default=60)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
start, end = datetime.fromisoformat(args.start), datetime.fromisoformat(args.end)
if start.tzinfo or end.tzinfo or start >= end:
    parser.error("Use increasing timestamps in the server log timezone, without UTC offsets")
logs = [path.resolve() for path in args.logs]
if len({path.parent for path in logs}) != 1:
    parser.error("Log files must be in one directory")
if args.output.resolve() in {args.report.resolve(), *logs}:
    parser.error("Output must differ from inputs")
artifact = read_artifact(args.report)
items = tuple(key for key in artifact["items"] if key.startswith("server_log."))
if not items:
    parser.error("Report has no server_log items")


class Shell:
    async def run_script_bytes(
        self, script, *, arguments=(), timeout=60, check=False, output_limit_bytes=None
    ):
        result = await asyncio.to_thread(
            subprocess.run,
            ["/bin/sh", "-s", "--", *arguments],
            input=script,
            capture_output=True,
            timeout=timeout,
        )
        if output_limit_bytes is not None and len(result.stdout) > output_limit_bytes:
            raise RuntimeError("Harvester exceeded its output budget")
        return SimpleNamespace(
            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr
        )


async def main():
    results = []
    for name, source in [
        ("local", LocalLogSource(str(logs[0].parent))),
        ("shell", BashHarvesterSource(Shell())),
    ]:
        request = ScanRequest(
            log_directory=str(logs[0].parent),
            files=tuple(
                LogFileInfo(
                    path.name, path.stat().st_size, datetime.fromtimestamp(path.stat().st_mtime)
                )
                for path in sorted(logs, key=lambda path: path.stat().st_mtime, reverse=True)
            ),
            window_from_ts=args.start,
            window_to_ts=args.end,
            recall_clauses=clauses_for_items(items),
            raw_record_cap=AUTO_EXPLAIN_RAW_RECORD_CAP,
            deadline_monotonic=time.monotonic() + args.timeout,
        )
        scan = await source.scan(request)
        window = _build_window(
            scan,
            depth_minutes=max(1, int((end - start).total_seconds() / 60)),
            server_version_num=artifact["runtime"]["server_version_num"],
            window_from=args.start,
            window_to=args.end,
            locale_supported=True,
            encodings={},
        )
        errors = Counter()
        for record in window.records:
            if record.severity in {"ERROR", "FATAL", "PANIC"}:
                errors[record.sql_state] += record.repeat_count
        results.append(
            {
                "source": name,
                "coverage": asdict(window.coverage),
                "plan_count": sum(
                    record.repeat_count for record in window.records if record.auto_explain_plan
                ),
                "errors": dict(errors),
            }
        )
    matched = all(results[0][key] == results[1][key] for key in ["plan_count", "errors"])
    complete = all(
        row["coverage"]["ranking_complete"] and not row["coverage"]["dropped_lines"]
        for row in results
    )
    write_json(args.output, {"results": results, "matched": matched, "complete": complete})
    print(f"Scanner counts match: {matched}; coverage complete: {complete}")
    return 0 if matched and complete else 1


raise SystemExit(asyncio.run(main()))
