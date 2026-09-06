"""Record hashes and item counts, or verify a saved manifest."""

import argparse
import json
from pathlib import Path

from common import inputs, read_artifact, sha256, write_json, check_output

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("reports", nargs="*", help="JSON/HTML files or quoted globs")
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--verify", type=Path)
args = parser.parse_args()
if args.verify:
    check_output(args.output, [args.verify])
    manifest = json.loads(args.verify.read_text())
    files = manifest["files"]
    check_output(args.output, [Path(entry["path"]) for entry in files])
    changed = [
        entry["path"]
        for entry in files
        if not Path(entry["path"]).is_file() or sha256(Path(entry["path"])) != entry["sha256"]
    ]
    write_json(args.output, {"checked_files": len(files), "changed_files": changed})
    print(f"{len(files)} files checked; {len(changed)} changed or missing")
    raise SystemExit(bool(changed))
files, reports, html = [], [], []
for suffix in [".json", ".html"]:
    try:
        paths = inputs(args.reports, suffix)
    except ValueError:
        continue
    for path in paths:
        check_output(args.output, [path])
        if path == args.output.resolve():
            parser.error("Output must differ from inputs")
        if suffix == ".json":
            artifact = read_artifact(path)
            reports.append(
                {"path": str(path), "items": len(artifact["items"]), "runtime": artifact["runtime"]}
            )
        else:
            html.append(str(path))
        files.append({"path": str(path), "sha256": sha256(path)})
if not files:
    parser.error("No inputs matched")
write_json(args.output, {"files": files, "reports": reports, "html": html})
print(f"{len(reports)} JSON artifacts; {len(html)} HTML reports; {len(files)} hashes")
