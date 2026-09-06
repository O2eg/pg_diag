import collections
import hashlib
import json
import math
from pathlib import Path
import argparse
from common import inputs, read_artifact, check_output, write_json

parser = argparse.ArgumentParser(
    description="Scan saved artifacts for evidence gaps and suspicious numeric/series values."
)
parser.add_argument("reports", nargs="+", help="JSON files or quoted glob patterns")
parser.add_argument("--output-dir", type=Path, required=True)
parser.add_argument(
    "--secret-file",
    type=Path,
    action="append",
    default=[],
    help="Optional known-secret file, or JSON with password fields; values are never printed",
)
args = parser.parse_args()
OUT = args.output_dir.resolve()
OUT.mkdir(parents=True, exist_ok=True)
paths = inputs(args.reports, ".json")
for name in ["scan.json", "item-evidence.json"]:
    check_output(OUT / name, paths)
summaries = []
candidates = []
catalog = collections.defaultdict(list)
secrets = []


def collect_passwords(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "password" and isinstance(item, str) and item:
                secrets.append(item.encode())
            else:
                collect_passwords(item)
    elif isinstance(value, list):
        for item in value:
            collect_passwords(item)


for secret_file in args.secret_file:
    for name in ["scan.json", "item-evidence.json"]:
        check_output(OUT / name, [secret_file])
    raw = secret_file.read_bytes().strip()
    if secret_file.suffix == ".json":
        collect_passwords(json.loads(raw))
    elif raw:
        secrets.append(raw)


def num(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def candidate(tag, key, kind, **kw):
    candidates.append({"report": tag, "item": key, "kind": kind, **kw})


for path in paths:
    a = read_artifact(path)
    tag = str(path)
    rt = a["runtime"]
    items = a["items"]
    totals = collections.Counter()
    snapshot_status = collections.Counter()
    diagnostics = []
    for file in [path, path.with_suffix(".html")]:
        if secrets and file.exists():
            raw = file.read_bytes()
            if any(secret in raw for secret in secrets):
                candidate(tag, "*", "known_secret_in_report", file=str(file))
    for sample in a.get("snapshots", []):
        for key, si in sample["items"].items():
            snapshot_status[si.get("collection_status")] += 1
    for key, it in items.items():
        r = it.get("result") or {}
        cols = r.get("columns", [])
        rows = r.get("rows", [])
        series = r.get("series", [])
        zeros = r.get("zero_series", [])
        if r.get("kind") == "table" and (
            r.get("row_count", len(rows)) != len(rows)
            or any(not isinstance(row, list) or len(row) != len(cols) for row in rows)
        ):
            candidate(
                tag,
                key,
                "table_shape",
                rows=len(rows),
                columns=len(cols),
                row_count=r.get("row_count"),
            )
        totals[it["collection_status"]] += 1
        missing = []
        numbers = {}
        badneg = []
        badpercent = []
        for j, c in enumerate(cols):
            if not isinstance(c, dict):
                continue
            vals = [row[j] for row in rows if isinstance(row, list) and j < len(row)]
            non = [v for v in vals if v is not None]
            if vals and not non:
                missing.append(c["name"])
            ns = [x for v in non if (x := num(v)) is not None]
            if ns:
                numbers[c["name"]] = {"min": min(ns), "max": max(ns), "count": len(ns)}
            if (
                ns
                and c.get("semantic_role") in ["counter", "counter_delta", "rate", "duration"]
                and min(ns) < 0
            ):
                badneg.append([c["name"], min(ns), c.get("unit")])
            if ns and c.get("unit") in {"percent", "%"} and (min(ns) < 0 or max(ns) > 100.00001):
                badpercent.append([c["name"], min(ns), max(ns)])
        if badneg:
            candidate(tag, key, "negative_measurement", columns=badneg)
        if badpercent:
            candidate(tag, key, "percentage_outside_0_100", columns=badpercent)
        if missing and rows:
            candidate(
                tag,
                key,
                "all_null_columns",
                columns=missing,
                row_count=len(rows),
                column_statuses=r.get("column_statuses"),
            )
        for s in series:
            points = s.get("points", [])
            times = [p.get("t") for p in points]
            values = [num(p.get("value")) for p in points]
            numeric = [v for v in values if v is not None]
            if all(isinstance(t, str) for t in times) and times != sorted(times):
                candidate(tag, key, "unordered_points", series=s["name"])
            if len(set(times)) != len(times):
                candidate(tag, key, "duplicate_timestamps", series=s["name"])
            if points and not numeric:
                candidate(tag, key, "all_null_series", series=s["name"], points=len(points))
            if (
                numeric
                and s.get("semantic_role") in ["rate", "counter", "counter_delta", "duration"]
                and min(numeric) < 0
            ):
                candidate(tag, key, "negative_chart_value", series=s["name"], minimum=min(numeric))
            if (
                numeric
                and s.get("unit") in {"percent", "%"}
                and (min(numeric) < 0 or max(numeric) > 100.00001)
            ):
                candidate(
                    tag,
                    key,
                    "chart_percentage_outside_0_100",
                    series=s["name"],
                    minimum=min(numeric),
                    maximum=max(numeric),
                )
        diags = it.get("diagnostics") or []
        if key == "snapshot_charts_os.os_cpu_utilization":
            states = {"user", "system", "iowait", "steal", "idle"}
            times = collections.defaultdict(dict)
            for line in series:
                if line["name"] in states:
                    for point in line.get("points", []):
                        if num(point.get("value")) is not None:
                            times[point["t"]][line["name"]] = num(point["value"])
            measured_zero = {
                line["name"]
                for line in zeros
                if line.get("sample_count") == len(times)
                and line.get("missing_count") == 0
                and len(times) >= 2
            }
            for timestamp, values in times.items():
                if set(values) | measured_zero >= states and not math.isclose(
                    sum(values.values()), 100, abs_tol=1e-6
                ):
                    candidate(
                        tag, key, "cpu_state_sum", timestamp=timestamp, total=sum(values.values())
                    )
        if diags:
            diagnostics.append({"item": key, "diagnostics": diags})
        ic = r.get("interval_coverage")
        if ic and ic.get("invalid"):
            candidate(tag, key, "invalid_intervals", coverage=ic)
        evidence = bool(
            rows
            or any(p.get("value") is not None for s in series for p in s.get("points", []))
            or any(z.get("sample_count", 0) > 0 for z in zeros)
            or (r.get("kind") == "plain_text" and r.get("data"))
        )
        catalog[key].append(
            {
                "report": tag,
                "status": it["collection_status"],
                "kind": r.get("kind"),
                "rows": len(rows),
                "series": len(series),
                "zero_series": len(zeros),
                "has_evidence": evidence,
                "null_columns": missing,
                "reason": it.get("reason"),
                "severity": it.get("severity_level"),
                "issues": it.get("issues"),
                "interval_coverage": ic,
                "numbers": numbers,
            }
        )
    summaries.append(
        {
            "report": tag,
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "items": len(items),
            "statuses": dict(totals),
            "snapshot_count": len(a.get("snapshots", [])),
            "snapshot_item_statuses": dict(snapshot_status),
            "runtime_diagnostics": a.get("diagnostics", []),
            "item_diagnostics": diagnostics,
            "log_coverage": (rt.get("log_collection") or {}).get("coverage"),
        }
    )
write_json(OUT / "scan.json", {"reports": summaries, "candidates": candidates})
write_json(OUT / "item-evidence.json", catalog)
print(
    "reports",
    len(summaries),
    "items",
    len(catalog),
    "candidates",
    dict(collections.Counter(c["kind"] for c in candidates)),
)
for kind in [
    "negative_measurement",
    "percentage_outside_0_100",
    "unordered_points",
    "duplicate_timestamps",
    "all_null_series",
    "negative_chart_value",
    "chart_percentage_outside_0_100",
]:
    vals = [c for c in candidates if c["kind"] == kind]
    print(kind, len(vals))
    print(json.dumps(vals[:15], indent=2))
print(
    "never with evidence", [k for k, v in catalog.items() if not any(x["has_evidence"] for x in v)]
)
