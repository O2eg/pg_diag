"""Small shared helpers for offline report checks; never connect to PostgreSQL."""

import glob
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "src/pg_diag/render/graph"
BUNDLE = [
    "pg-diag-graph-data.js",
    "pg-diag-graph-rules.js",
    "pg-diag-graph-groups.js",
    "pg-diag-graph.js",
]


def inputs(patterns, suffix):
    paths = sorted(
        {
            Path(p).resolve()
            for pattern in patterns
            for p in glob.glob(pattern, recursive=True)
            if Path(p).is_file() and Path(p).suffix == suffix
        }
    )
    if not paths:
        raise ValueError(f"No {suffix} inputs matched")
    return paths


def read_artifact(path):
    value = json.loads(path.read_text())
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("items"), dict)
        or "runtime" not in value
    ):
        raise ValueError(f"Not a pg_diag artifact: {path}")
    return value


def sha256(path):
    with path.open("rb") as source:
        digest = hashlib.sha256()
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_output(path, sources):
    protected = set()
    for source in sources:
        source = source.resolve()
        protected.add(source)
        if source.suffix in {".json", ".html"}:
            protected.update({source.with_suffix(".json"), source.with_suffix(".html")})
    if path.resolve() in protected:
        raise ValueError(f"Output would overwrite an input or its companion: {path}")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Reports can contain SQL and host information; retain private permissions.
    with open(
        path, "w", opener=lambda name, flags: __import__("os").open(name, flags, 0o600)
    ) as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write("\n")


def asset_pattern(name, tag):
    return re.compile(
        r"(<" + tag + r'\b[^>]*\bid="' + re.escape(name) + r'"[^>]*>)(.*?)(</' + tag + r">)", re.S
    )


def assets():
    # Match the escaping used by the production HTML renderer.
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from pg_diag.render.html import _inline_script, _inline_style

    return {
        "pg-diag-graph-css": ("style", _inline_style((GRAPH / "pg-diag-graph.css").read_text())),
        "pg-diag-graph-definition": (
            "script",
            _inline_script((GRAPH / "graph.json").read_text().strip()),
        ),
        "pg-diag-graph-library": (
            "script",
            _inline_script("\n".join((GRAPH / name).read_text() for name in BUNDLE)),
        ),
        "pg-diag-graph-render-library": (
            "script",
            _inline_script((GRAPH / "pg-diag-graph-render.js").read_text()),
        ),
    }


def refresh(text):
    before = text
    parts = assets()
    for name, (tag, body) in parts.items():
        pattern = asset_pattern(name, tag)
        if len(pattern.findall(text)) != 1:
            raise ValueError(f"Expected exactly one {name} block")
        text = pattern.sub(lambda m: m[1] + body + m[3], text)
    stripped = []
    for value in (before, text):
        for name, (tag, _) in parts.items():
            value = asset_pattern(name, tag).sub(lambda m: m[1] + m[3], value)
        stripped.append(value)
    if stripped[0] != stripped[1]:
        raise ValueError("Non-graph HTML changed")
    return text
