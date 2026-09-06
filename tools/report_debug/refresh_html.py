"""Replace only the four graph asset blocks in one already built HTML."""

import argparse
import shutil
from pathlib import Path

from common import refresh, sha256

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("report", type=Path)
parser.add_argument("--output", type=Path, help="Write a copy; default: update the supplied HTML")
parser.add_argument("--backup", type=Path, help="Required when updating the original HTML")
args = parser.parse_args()
source = args.report.resolve()
target = (args.output or args.report).resolve()
if source.suffix != ".html" or target.suffix != ".html":
    parser.error("Input and output must be HTML files")
before = source.read_bytes().decode("utf-8")
after = refresh(before)
if target == source:
    if not args.backup or args.backup.resolve() in {source, source.with_suffix(".json")}:
        parser.error("Provide a distinct --backup path for an in-place update")
    backup = args.backup.resolve()
    if backup.exists():
        parser.error("Backup already exists; choose a new path")
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, backup)
elif target.exists():
    parser.error("Output already exists; choose a new path")
target.parent.mkdir(parents=True, exist_ok=True)
with open(
    target,
    "w",
    encoding="utf-8",
    newline="",
    opener=lambda name, flags: __import__("os").open(name, flags, 0o600),
) as out:
    out.write(after)
print(f"Updated four graph blocks; report data and other markup unchanged: {target}")
print(f"SHA256: {sha256(target)}")
