"""Verify that wheel and sdist contain every tracked Markdown file, byte for byte."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import tarfile
import zipfile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path, help="Directory containing one wheel and one sdist")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    documents = [
        Path(name)
        for name in subprocess.check_output(
            ["git", "ls-files", "-z", "*.md"], cwd=root, text=True,
        ).split("\0")
        if name
    ]
    wheels = list(args.dist.glob("*.whl"))
    sdists = list(args.dist.glob("*.tar.gz"))
    if not documents or len(wheels) != 1 or len(sdists) != 1:
        parser.error("Expected tracked Markdown files, exactly one wheel, and exactly one sdist")

    failures = []
    with zipfile.ZipFile(wheels[0]) as wheel, tarfile.open(sdists[0], "r:gz") as sdist:
        wheel_names = set(wheel.namelist())
        sdist_names = set(sdist.getnames())
        data_root = wheels[0].name.split("-", 2)
        data_prefix = f"{data_root[0]}-{data_root[1]}.data/data/share/doc/pg-diag"
        sdist_prefix = sdists[0].name.removesuffix(".tar.gz")
        for document in documents:
            expected = (root / document).read_bytes()
            source_name = f"{sdist_prefix}/{document.as_posix()}"
            wheel_name = (
                document.relative_to("src").as_posix()
                if document.is_relative_to("src/pg_diag")
                else f"{data_prefix}/{document.as_posix()}"
            )
            if source_name not in sdist_names:
                failures.append(f"sdist missing: {document}")
            else:
                handle = sdist.extractfile(source_name)
                if handle is None or handle.read() != expected:
                    failures.append(f"sdist content mismatch: {document}")
            if wheel_name not in wheel_names:
                failures.append(f"wheel missing: {document}")
            elif wheel.read(wheel_name) != expected:
                failures.append(f"wheel content mismatch: {document}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"OK: all {len(documents)} Markdown files match in wheel and sdist")


if __name__ == "__main__":
    main()
