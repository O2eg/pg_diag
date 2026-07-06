"""Load pg_diag declarative content packs."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml

from .errors import ContentLoadError


class UniqueKeySafeLoader(yaml.SafeLoader):
    """PyYAML safe loader that rejects duplicate mapping keys."""


def _construct_mapping(loader: UniqueKeySafeLoader, node: yaml.nodes.MappingNode, deep: bool = False):
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            mark = key_node.start_mark
            raise ContentLoadError(
                f"Duplicate YAML key {key!r} at {mark.name}:{mark.line + 1}:{mark.column + 1}"
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


@dataclass(frozen=True)
class ContentPack:
    path: Path
    report: dict[str, Any]
    query_catalog: dict[str, Any]
    script_catalog: dict[str, Any]
    metric_catalog: dict[str, Any]
    instructions: dict[str, dict[str, str]]
    queries: dict[str, dict[str, Any]]
    scripts: dict[str, dict[str, Any]]
    metrics: dict[str, dict[str, Any]]
    catalog_files: list[Path]
    checksum: str


def load_yaml_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.load(handle, Loader=UniqueKeySafeLoader)
    except ContentLoadError:
        raise
    except OSError as exc:
        raise ContentLoadError(f"Cannot read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ContentLoadError(f"Cannot parse YAML {path}: {exc}") from exc

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ContentLoadError(f"YAML root must be a mapping: {path}")
    return data


def _merge_defaults(defaults: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(defaults)
    for key, item_value in value.items():
        if isinstance(item_value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_defaults(result[key], item_value)
        else:
            result[key] = deepcopy(item_value)
    return result


def _content_checksum(paths: list[Path], root: Path) -> str:
    digest = sha256()
    for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def instruction_ref_for_report_item(section_id: str, item_key: str, item: dict[str, Any]) -> str | None:
    ref = item.get("instruction")
    if ref is None:
        ref = item.get("instructions")
    if ref is False:
        return None
    if ref is None:
        return f"items/{section_id}/{item_key}.md"
    if not isinstance(ref, str) or not ref:
        raise ContentLoadError(
            f"Instruction path must be a non-empty string or false: sections.{section_id}.items.{item_key}"
        )
    return ref


def _instruction_path(instructions_dir: Path, instruction_ref: str) -> Path:
    path_ref = Path(instruction_ref)
    if path_ref.is_absolute() or ".." in path_ref.parts:
        raise ContentLoadError(f"Instruction path must stay under the instructions directory: {instruction_ref}")
    return instructions_dir / path_ref


def load_content(content_path: str | Path) -> ContentPack:
    root = Path(content_path).resolve()
    if not root.exists():
        raise ContentLoadError(f"Content path does not exist: {root}")
    if not root.is_dir():
        raise ContentLoadError(f"Content path must be a directory: {root}")

    report_path = root / "report.yaml"
    report = load_yaml_file(report_path)
    catalogs = (report.get("report") or {}).get("catalogs") or {}

    query_index_path = root / catalogs.get("queries", "queries.yaml")
    script_path = root / catalogs.get("scripts", "scripts.yaml")
    metric_path = root / catalogs.get("metrics", "metrics.yaml")
    instructions_root = catalogs.get("instructions", "instructions")

    query_index = load_yaml_file(query_index_path)
    script_catalog = load_yaml_file(script_path)
    metric_catalog = load_yaml_file(metric_path)

    query_catalog = query_index.get("query_catalog")
    if not isinstance(query_catalog, dict):
        raise ContentLoadError(f"Missing query_catalog mapping in {query_index_path}")

    query_defaults = query_catalog.get("defaults") or {}
    catalog_files: list[Path] = []
    queries: dict[str, dict[str, Any]] = {}
    for catalog_ref in query_catalog.get("files", []) or []:
        catalog_path = (root / catalog_ref).resolve()
        catalog_files.append(catalog_path)
        catalog_data = load_yaml_file(catalog_path)
        catalog_queries = catalog_data.get("queries") or {}
        if not isinstance(catalog_queries, dict):
            raise ContentLoadError(f"queries must be a mapping in {catalog_path}")
        for query_id, manifest in catalog_queries.items():
            if query_id in queries:
                raise ContentLoadError(f"Duplicate query id {query_id!r} in {catalog_path}")
            if not isinstance(manifest, dict):
                raise ContentLoadError(f"Query manifest must be a mapping: {query_id}")
            queries[query_id] = _merge_defaults(query_defaults, manifest)

    scripts_root = script_catalog.get("scripts") or {}
    script_defaults = (script_catalog.get("script_catalog") or {}).get("defaults") or {}
    scripts = {
        script_id: _merge_defaults(script_defaults, script)
        for script_id, script in scripts_root.items()
    }

    metrics_root = metric_catalog.get("metrics") or {}
    metric_defaults = (metric_catalog.get("metric_catalog") or {}).get("defaults") or {}
    metrics = {
        metric_id: _merge_defaults(metric_defaults, metric)
        for metric_id, metric in metrics_root.items()
    }

    instructions_dir = root / instructions_root
    instructions: dict[str, dict[str, str]] = {}
    if instructions_dir.exists():
        for section_id, item_key, item_id, item in iter_report_items_from_report(report):
            instruction_ref = instruction_ref_for_report_item(section_id, item_key, item)
            if instruction_ref is None:
                continue
            path = _instruction_path(instructions_dir, instruction_ref)
            if path.exists() and path.is_file():
                instructions[item_id] = {
                    "format": "markdown",
                    "path": f"{instructions_root}/{instruction_ref}",
                    "text": path.read_text(encoding="utf-8"),
                }

    instruction_files = []
    if instructions_dir.exists():
        instruction_files = sorted(instructions_dir.rglob("*.md"))

    checksum_paths = [
        report_path,
        query_index_path,
        script_path,
        metric_path,
        *catalog_files,
        *sorted((root / "queries").rglob("*.sql")),
        *sorted((root / "scripts").rglob("*")),
        *instruction_files,
    ]
    checksum_paths = [path for path in checksum_paths if path.is_file()]

    return ContentPack(
        path=root,
        report=report,
        query_catalog=query_index,
        script_catalog=script_catalog,
        metric_catalog=metric_catalog,
        instructions=instructions,
        queries=queries,
        scripts=scripts,
        metrics=metrics,
        catalog_files=catalog_files,
        checksum=_content_checksum(checksum_paths, root),
    )


def iter_report_items(content: ContentPack):
    yield from iter_report_items_from_report(content.report)


def iter_report_items_from_report(report: dict[str, Any]):
    sections = report.get("sections") or {}
    for section_id, section in sections.items():
        items = (section or {}).get("items") or {}
        for item_key, item in items.items():
            yield section_id, item_key, f"{section_id}.{item_key}", item or {}
