"""Offline replay and independent arithmetic checks of saved experiment artifacts."""

import json
import math
from pathlib import Path
from pg_diag.content_loader import load_content
from pg_diag.versioning import select_query_variant
from pg_diag.metric_engine import build_chart_result
import argparse
from common import ROOT, inputs, read_artifact, check_output, write_json

parser = argparse.ArgumentParser(
    description="Replay retained metric samples and check rate/ratio arithmetic without altering artifacts."
)
parser.add_argument("reports", nargs="+")
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
C = load_content(ROOT / "src/pg_diag/content")
paths = inputs(args.reports, ".json")
check_output(args.output, paths)
if args.output.resolve() in paths:
    parser.error("Output must differ from inputs")
args.output.parent.mkdir(parents=True, exist_ok=True)

out = []


def point_values(result):
    return {
        s["name"]: [
            (p["t"].replace("+00:00", "Z"), None if p["value"] is None else float(p["value"]))
            for p in s["points"]
        ]
        for s in result.get("series", [])
        if s.get("points")
    }


def same_points(a, b):
    if set(a) != set(b):
        return False
    for key in a:
        if len(a[key]) != len(b[key]):
            return False
        for (ta, va), (tb, vb) in zip(a[key], b[key]):
            if ta != tb or (va is None) != (vb is None):
                return False
            if va is not None and not math.isclose(va, vb, rel_tol=1e-9, abs_tol=1e-12):
                return False
    return True


for path in paths:
    a = read_artifact(path)
    stats = {
        "report": str(path),
        "charts_replayed": 0,
        "chart_mismatches": [],
        "rates_checked": 0,
        "ratios_checked": 0,
        "arithmetic_mismatches": [],
        "reference_errors": [],
    }
    for key, it in a["items"].items():
        meta = it.get("source_metadata") or {}
        result = it.get("result") or {}
        mid = meta.get("metric_id") or meta.get("metric")
        if not mid:
            sec, item = key.split(".", 1)
            mid = (C.report["sections"].get(sec, {}).get("items", {}).get(item, {}) or {}).get(
                "metric"
            )
        m = C.metrics.get(mid or "", {})
        src = m.get("source_query")
        schema = a.get("snapshot_schemas", {}).get(src)
        if result.get("kind") == "chart" and schema:
            query = C.queries[src]
            sem = select_query_variant(
                query["title"], query, a["runtime"]["server_version_num"]
            ).variant.get("semantic_columns", {})
            names = [c["name"] for c in schema["columns"]]
            samples = []
            for snap in a["snapshots"]:
                si = snap.get("items", {}).get(src)
                if si is not None:
                    samples.append(
                        {
                            "timestamp": snap["timestamp"],
                            "rows": [
                                dict(zip(names, row))
                                for row in si.get("result", {}).get("rows", [])
                            ],
                        }
                    )
            rebuilt = build_chart_result(m, samples, sem)
            stats["charts_replayed"] += 1
            if not same_points(point_values(result), point_values(rebuilt)):
                stats["chart_mismatches"].append(key)
        cols = m.get("table", {}).get("columns", [])
        refs = {c.get("value_ref"): c["name"] for c in cols if c.get("transform") == "delta"}
        duration = result.get("delta_window", {}).get("duration_seconds")
        for row in result.get("rows", []):
            d = dict(zip([c["name"] for c in result.get("columns", [])], row))
            for c in cols:
                value = d.get(c["name"])
                expected = None
                kind = None
                if value is None:
                    continue
                if c.get("transform") == "rate" and c.get("value_ref") in refs and duration:
                    raw = d.get(refs[c["value_ref"]])
                    expected = float(raw) / duration if raw is not None else None
                    kind = "rates"
                elif c.get("transform") == "delta_ratio":
                    nr = c.get("numerator_refs") or [c.get("numerator_ref")]
                    dr = c.get("denominator_refs") or [c.get("denominator_ref")]
                    if all(ref in refs and d.get(refs[ref]) is not None for ref in nr + dr):
                        n = sum(float(d[refs[ref]]) for ref in nr)
                        den = sum(float(d[refs[ref]]) for ref in dr)
                        if den:
                            expected = n / den * float(c.get("scale", 1))
                            kind = "ratios"
                if expected is not None:
                    stats[kind + "_checked"] += 1
                    # Source statement timestamps differ slightly from scheduler endpoint time stored in delta_window.
                    if not math.isclose(
                        float(value),
                        expected,
                        rel_tol=0.002 if kind == "rates" else 1e-9,
                        abs_tol=1e-8,
                    ):
                        stats["arithmetic_mismatches"].append(
                            {
                                "item": key,
                                "column": c["name"],
                                "actual": value,
                                "expected": expected,
                            }
                        )

        # Verify every explicit query/plan link in result data resolves.
        def walk(v):
            if isinstance(v, dict):
                for k, w in v.items():
                    if k in ("plan_ref", "query_ref"):
                        pool = result.get("references", {}).get(
                            "plans" if k == "plan_ref" else "queries", {}
                        )
                        if w is not None and w not in pool:
                            stats["reference_errors"].append([key, k, w])
                    else:
                        walk(w)
            elif isinstance(v, list):
                for w in v:
                    walk(w)

        walk(result)
    out.append(stats)
    print(json.dumps(stats), flush=True)
write_json(args.output, out)
