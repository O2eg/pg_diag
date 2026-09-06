"""Tabulate graph evaluations and compare against a previous evaluation file."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from common import write_json, check_output


def category(node):
    if not any(
        b["presence"] in {"present", "empty"} for b in node.get("inputBindings", node["bindings"])
    ):
        return "missing"
    hints = " ".join(node["hints"]).lower()
    if any(word in hints for word in ("incomplete", "truncated", "degraded")):
        return "incomplete"
    if (
        node["evaluator"]
        in {
            "reference",
            "platform_facts",
            "network_inventory",
            "network_settings",
            "network_roundtrips",
        }
        or "clientread duration" in hints
    ):
        return "reference"
    if any(
        word in hints
        for word in ("baseline", "policy", "upstream primary", "global connection controls")
    ):
        return "baseline"
    return "missing"


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("evaluation", type=Path)
parser.add_argument("--before", type=Path)
parser.add_argument("--output-dir", type=Path, required=True)
args = parser.parse_args()
for name in ["matrix.json", "unassessed.json", "changes.json", "nodes.tsv"]:
    check_output(args.output_dir / name, [args.evaluation] + ([args.before] if args.before else []))
reports = json.loads(args.evaluation.read_text())
before = {r["path"]: r for r in json.loads(args.before.read_text())} if args.before else {}
rows, grey, changes, matrix = [], [], [], []
for report in reports:
    counts = Counter()
    for node in report["nodes"].values():
        kind = category(node) if node["status"] == "no_data" else ""
        if kind:
            counts[kind] += 1
            grey.append(
                {
                    "report": report["path"],
                    "node": node["id"],
                    "category": kind,
                    "hints": node["hints"],
                }
            )
        rows.append(
            [
                report["path"],
                node["id"],
                node["label"],
                node["ownStatus"],
                node["status"],
                kind,
                " | ".join(node["hints"]),
            ]
        )
        old = before.get(report["path"], {}).get("nodes", {}).get(node["id"])
        fields = ["ownScore", "status", "facts", "reasons", "hints"]
        if old and any(old[key] != node[key] for key in fields):
            changes.append(
                {
                    "report": report["path"],
                    "node": node["id"],
                    "before": {key: old[key] for key in fields},
                    "after": {key: node[key] for key in fields},
                }
            )
    matrix.append(
        {
            "report": report["path"],
            "coverage": report["coverage"],
            "grey_categories": dict(counts),
            "errors": report["errors"],
            "contradictions": report["contradictions"],
        }
    )
for name, value in [("matrix", matrix), ("unassessed", grey), ("changes", changes)]:
    write_json(args.output_dir / (name + ".json"), value)
with (args.output_dir / "nodes.tsv").open("w", newline="") as out:
    writer = csv.writer(out, delimiter="\t")
    writer.writerow(
        ["report", "node", "label", "own_status", "status", "unassessed_category", "explanation"]
    )
    writer.writerows(rows)
print(f"{len(reports)} reports, {len(rows)} nodes, {len(changes)} changed node evaluations")
print("Grey categories are a triage heuristic; inspect the recorded assessment limits.")
