"""Independently count CSV log events within explicitly supplied UTC boundaries."""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
from pathlib import Path
import re

from common import read_artifact, write_json


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace(" UTC", "+00:00").replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must contain a UTC offset")
    return parsed.astimezone(timezone.utc)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("report", type=Path)
parser.add_argument("logs", type=Path, nargs="+")
parser.add_argument("--from", dest="start", required=True)
parser.add_argument("--to", dest="end", required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument(
    "--top-per-minute", type=int, help="Compare retained plan markers against this configured top-N"
)
args = parser.parse_args()
start, end = timestamp(args.start), timestamp(args.end)
if start >= end:
    parser.error("Start must precede end")
if args.top_per_minute is not None and args.top_per_minute < 1:
    parser.error("--top-per-minute must be positive")
if args.output.resolve() in {args.report.resolve(), *(path.resolve() for path in args.logs)}:
    parser.error("Output must differ from inputs")
artifact = read_artifact(args.report)
csv.field_size_limit(16 * 1024 * 1024)
levels, states = Counter(), Counter()
plans = malformed = 0
plan_buckets = defaultdict(list)
for path in args.logs:
    with path.open(newline="") as source:
        for row in csv.reader(source):
            if len(row) < 23:
                malformed += 1
                continue
            if not start <= timestamp(row[0]) <= end:
                continue
            levels[row[11]] += 1
            if row[11] in {"ERROR", "FATAL", "PANIC"}:
                states[row[12]] += 1
            match = re.match(r"duration:\s*([0-9.]+)\s*ms\s+plan:", row[13])
            if match:
                plans += 1
                if args.top_per_minute:
                    time = timestamp(row[0])
                    bucket = plan_buckets[time.replace(second=0, microsecond=0)]
                    bucket.append((time, float(match[1])))
                    bucket.sort(key=lambda record: (-record[1], record[0]))
                    del bucket[args.top_per_minute :]


def rows(item_id):
    result = artifact["items"].get(item_id, {}).get("result") or {}
    return [
        dict(zip([column["name"] for column in result.get("columns", [])], row))
        for row in result.get("rows", [])
    ]


reported = Counter()
for row in rows("server_log.top_errors"):
    reported[row.get("sql_state")] += int(row.get("occurrences") or 0)
plan_result = artifact["items"].get("server_log.auto_explain_plans", {}).get("result") or {}
comparison = {
    "window": [args.start, args.end],
    "raw_plan_count": plans,
    "reported_plan_count": plan_result.get("plan_count"),
    "raw_error_states": dict(states),
    "reported_error_states": dict(reported),
    "raw_warning_count": levels["WARNING"],
    "reported_warning_count": sum(
        int(row.get("occurrences") or 0) for row in rows("server_log.top_warnings")
    ),
    "malformed_records": malformed,
    "coverage": artifact["runtime"].get("log_collection", {}).get("coverage"),
    "note": "Differences are candidates: verify window, log completeness, selected items and top-N limits.",
}
if args.top_per_minute:
    expected = {
        (time.isoformat(timespec="milliseconds"), duration)
        for bucket in plan_buckets.values()
        for time, duration in bucket
    }
    actual = {
        (
            timestamp(point["tooltip"]["log_time"]).isoformat(timespec="milliseconds"),
            float(point["value"]),
        )
        for series in plan_result.get("series", [])
        for point in series.get("points", [])
        if point.get("viewer")
    }
    comparison["top_plan_points"] = {
        "per_minute": args.top_per_minute,
        "missing": sorted(expected - actual),
        "extra": sorted(actual - expected),
    }
write_json(args.output, comparison)
print(
    f'Raw plans: {plans}; reported: {plan_result.get("plan_count")}; malformed CSV records: {malformed}'
)
