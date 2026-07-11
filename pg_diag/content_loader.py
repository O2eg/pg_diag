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
        try:
            duplicate = key in mapping
        except TypeError as exc:
            mark = key_node.start_mark
            raise ContentLoadError(
                f"YAML mapping key must be hashable at "
                f"{mark.name}:{mark.line + 1}:{mark.column + 1}"
            ) from exc
        if duplicate:
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
    python_catalog: dict[str, Any]
    field_reference_catalog: dict[str, Any]
    instructions: dict[str, dict[str, str]]
    queries: dict[str, dict[str, Any]]
    scripts: dict[str, dict[str, Any]]
    metrics: dict[str, dict[str, Any]]
    pythons: dict[str, dict[str, Any]]
    sampler_providers: dict[str, dict[str, Any]]
    document: dict[str, Any]
    provenance: dict[str, list[str]]
    catalog_files: list[Path]
    checksum: str


def load_yaml_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.load(handle, Loader=UniqueKeySafeLoader)
    except ContentLoadError:
        raise
    except (OSError, UnicodeError) as exc:
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


def resolve_under(base: str | Path, ref: Any, label: str) -> Path:
    """Resolve a content reference without allowing it to escape its declared root."""
    if not isinstance(ref, str) or not ref.strip():
        raise ContentLoadError(f"{label} must be a non-empty relative path")
    relative = Path(ref)
    if relative.is_absolute() or ".." in relative.parts:
        raise ContentLoadError(f"{label} must stay under {Path(base)}: {ref}")
    root = Path(base).resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ContentLoadError(f"{label} must stay under {root}: {ref}") from exc
    return candidate


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContentLoadError(f"{label} must be a mapping")
    return value


def _manifest_mapping(
    value: Any,
    defaults: dict[str, Any],
    label: str,
) -> dict[str, dict[str, Any]]:
    manifests = _mapping(value, label)
    result: dict[str, dict[str, Any]] = {}
    for source_id, manifest in manifests.items():
        if not isinstance(source_id, str) or not source_id:
            raise ContentLoadError(f"{label} ids must be non-empty strings: {source_id!r}")
        if not isinstance(manifest, dict):
            raise ContentLoadError(f"{label} manifest must be a mapping: {source_id}")
        result[source_id] = _merge_defaults(defaults, manifest)
    return result


def _content_checksum(paths: list[Path], root: Path) -> str:
    digest = sha256()
    for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
        resolved = path.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ContentLoadError(f"Checksum input must stay under content root: {path}") from exc
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        try:
            data = resolved.read_bytes()
        except OSError as exc:
            raise ContentLoadError(f"Cannot checksum {path}: {exc}") from exc
        digest.update(data)
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _relative_content_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def _build_content_document(
    *,
    report: dict[str, Any],
    query_catalog: dict[str, Any],
    script_catalog: dict[str, Any],
    metric_catalog: dict[str, Any],
    python_catalog: dict[str, Any],
    field_reference_catalog: dict[str, Any],
    queries: dict[str, dict[str, Any]],
    scripts: dict[str, dict[str, Any]],
    metrics: dict[str, dict[str, Any]],
    pythons: dict[str, dict[str, Any]],
    sampler_providers: dict[str, dict[str, Any]],
    instructions: dict[str, dict[str, str]],
) -> dict[str, Any]:
    reference_meta = _mapping(
        field_reference_catalog.get("field_reference"),
        "field_reference.yaml:field_reference",
    )
    instruction_refs = {
        item_id: {key: value for key, value in instruction.items() if key != "text"}
        for item_id, instruction in instructions.items()
    }
    return {
        "report": deepcopy(_mapping(report.get("report"), "report.yaml:report")),
        "runtime_policy": deepcopy(
            _mapping(report.get("runtime_policy"), "report.yaml:runtime_policy")
        ),
        "defaults": deepcopy(_mapping(report.get("defaults"), "report.yaml:defaults")),
        "sections": deepcopy(_mapping(report.get("sections"), "report.yaml:sections")),
        "catalogs": {
            "queries": deepcopy(
                _mapping(query_catalog.get("query_catalog"), "queries.yaml:query_catalog")
            ),
            "scripts": deepcopy(
                _mapping(script_catalog.get("script_catalog"), "scripts.yaml:script_catalog")
            ),
            "metrics": deepcopy(
                _mapping(metric_catalog.get("metric_catalog"), "metrics.yaml:metric_catalog")
            ),
            "python": deepcopy(
                _mapping(python_catalog.get("python_catalog"), "python.yaml:python_catalog")
            ),
        },
        "queries": deepcopy(queries),
        "scripts": deepcopy(scripts),
        "metrics": deepcopy(metrics),
        "python_sources": deepcopy(pythons),
        "sampler_providers": deepcopy(sampler_providers),
        "instructions": instruction_refs,
        "field_reference": deepcopy(
            _mapping(reference_meta.get("fields"), "field_reference.yaml:field_reference.fields")
        ),
    }


def _build_content_provenance(
    *,
    root: Path,
    report_path: Path,
    query_index_path: Path,
    script_path: Path,
    metric_path: Path,
    python_path: Path,
    field_reference_path: Path,
    query_source_files: dict[str, Path],
    queries: dict[str, dict[str, Any]],
    scripts: dict[str, dict[str, Any]],
    metrics: dict[str, dict[str, Any]],
    pythons: dict[str, dict[str, Any]],
    sampler_providers: dict[str, dict[str, Any]],
    instructions: dict[str, dict[str, str]],
) -> dict[str, list[str]]:
    report_source = [_relative_content_path(root, report_path)]
    query_index_source = _relative_content_path(root, query_index_path)
    provenance: dict[str, list[str]] = {
        "report": report_source,
        "runtime_policy": report_source,
        "defaults": report_source,
        "sections": report_source,
        "catalogs/queries": [query_index_source],
        "catalogs/scripts": [_relative_content_path(root, script_path)],
        "catalogs/metrics": [_relative_content_path(root, metric_path)],
        "catalogs/python": [_relative_content_path(root, python_path)],
    }
    provenance["field_reference"] = [_relative_content_path(root, field_reference_path)]
    for query_id in queries:
        sources = [query_index_source]
        source = _relative_content_path(root, query_source_files[query_id])
        if source not in sources:
            sources.append(source)
        provenance[f"queries/{query_id}"] = sources
    script_source = [_relative_content_path(root, script_path)]
    metric_source = [_relative_content_path(root, metric_path)]
    python_source = [_relative_content_path(root, python_path)]
    if scripts:
        provenance["scripts"] = script_source
    if metrics:
        provenance["metrics"] = metric_source
    if pythons:
        provenance["python_sources"] = python_source
    if sampler_providers:
        provenance["sampler_providers"] = metric_source
    for item_id, instruction in instructions.items():
        path = instruction.get("path")
        if path:
            provenance[f"instructions/{item_id}"] = [path]
    return provenance


def instruction_ref_for_report_item(section_id: str, item_key: str, item: dict[str, Any]) -> str | None:
    ref = item.get("instruction")
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
    return resolve_under(instructions_dir, instruction_ref, "Instruction path")


def load_content(content_path: str | Path) -> ContentPack:
    root = Path(content_path).resolve()
    if not root.exists():
        raise ContentLoadError(f"Content path does not exist: {root}")
    if not root.is_dir():
        raise ContentLoadError(f"Content path must be a directory: {root}")

    report_path = root / "report.yaml"
    report = load_yaml_file(report_path)
    report_meta = _mapping(report.get("report"), "report.yaml:report")
    catalogs = _mapping(report_meta.get("catalogs"), "report.yaml:report.catalogs")

    query_index_path = resolve_under(root, catalogs.get("queries"), "Query catalog path")
    script_path = resolve_under(root, catalogs.get("scripts"), "Script catalog path")
    metric_path = resolve_under(root, catalogs.get("metrics"), "Metric catalog path")
    python_path = resolve_under(root, catalogs.get("python"), "Python catalog path")
    field_reference_path = resolve_under(
        root,
        catalogs.get("field_reference"),
        "Field reference path",
    )
    instructions_root = catalogs.get("instructions")
    instructions_dir = resolve_under(root, instructions_root, "Instructions root")
    if not instructions_dir.is_dir():
        raise ContentLoadError(f"Instructions root must be a directory: {instructions_dir}")

    query_index = load_yaml_file(query_index_path)
    script_catalog = load_yaml_file(script_path)
    metric_catalog = load_yaml_file(metric_path)
    python_catalog = load_yaml_file(python_path)
    field_reference_catalog = load_yaml_file(field_reference_path)

    query_catalog = query_index.get("query_catalog")
    if not isinstance(query_catalog, dict):
        raise ContentLoadError(f"Missing query_catalog mapping in {query_index_path}")

    query_defaults = _mapping(
        query_catalog.get("defaults"),
        f"{query_index_path}:query_catalog.defaults",
    )
    catalog_refs = query_catalog.get("files")
    if not isinstance(catalog_refs, list) or not catalog_refs:
        raise ContentLoadError(f"query_catalog.files must be a non-empty list in {query_index_path}")
    catalog_files: list[Path] = []
    queries: dict[str, dict[str, Any]] = {}
    query_source_files: dict[str, Path] = {}
    for catalog_ref in catalog_refs:
        catalog_path = resolve_under(root, catalog_ref, "Query manifest catalog path")
        catalog_files.append(catalog_path)
        catalog_data = load_yaml_file(catalog_path)
        catalog_queries = _mapping(
            catalog_data.get("queries"),
            f"queries in {catalog_path}",
        )
        for query_id, manifest in catalog_queries.items():
            if not isinstance(query_id, str) or not query_id:
                raise ContentLoadError(f"Query ids must be non-empty strings in {catalog_path}")
            if query_id in queries:
                raise ContentLoadError(f"Duplicate query id {query_id!r} in {catalog_path}")
            if not isinstance(manifest, dict):
                raise ContentLoadError(f"Query manifest must be a mapping: {query_id}")
            queries[query_id] = _merge_defaults(query_defaults, manifest)
            query_source_files[query_id] = catalog_path

    script_catalog_meta = _mapping(
        script_catalog.get("script_catalog"),
        f"{script_path}:script_catalog",
    )
    script_defaults = _mapping(
        script_catalog_meta.get("defaults"),
        f"{script_path}:script_catalog.defaults",
    )
    scripts = _manifest_mapping(script_catalog.get("scripts"), script_defaults, "scripts")

    metric_catalog_meta = _mapping(
        metric_catalog.get("metric_catalog"),
        f"{metric_path}:metric_catalog",
    )
    metric_defaults = _mapping(
        metric_catalog_meta.get("defaults"),
        f"{metric_path}:metric_catalog.defaults",
    )
    metrics = _manifest_mapping(metric_catalog.get("metrics"), metric_defaults, "metrics")
    sampler_providers = _manifest_mapping(
        metric_catalog.get("sampler_providers"),
        {},
        "sampler_providers",
    )

    python_catalog_meta = _mapping(
        python_catalog.get("python_catalog"),
        f"{python_path}:python_catalog",
    )
    python_defaults = _mapping(
        python_catalog_meta.get("defaults"),
        f"{python_path}:python_catalog.defaults",
    )
    pythons = _manifest_mapping(
        python_catalog.get("python_sources"),
        python_defaults,
        "python_sources",
    )

    instructions: dict[str, dict[str, str]] = {}
    for section_id, item_key, item_id, item in iter_report_items_from_report(report):
        instruction_ref = instruction_ref_for_report_item(section_id, item_key, item)
        if instruction_ref is None:
            continue
        path = _instruction_path(instructions_dir, instruction_ref)
        if not path.is_file():
            raise ContentLoadError(f"Instruction file does not exist: {path}")
        try:
            instruction_text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ContentLoadError(f"Cannot read instruction {path}: {exc}") from exc
        instructions[item_id] = {
            "format": "markdown",
            "path": f"{instructions_root}/{instruction_ref}",
            "text": instruction_text,
        }

    instruction_files = sorted(instructions_dir.rglob("*.md"))

    sql_root_ref = query_catalog.get("sql_root")
    sql_root_path = resolve_under(root, sql_root_ref, "SQL root")
    scripts_root_path = resolve_under(root, "scripts", "Scripts root")
    python_root_path = resolve_under(root, "python", "Python root")
    checksum_paths = [
        report_path,
        query_index_path,
        script_path,
        metric_path,
        python_path,
        field_reference_path,
        *catalog_files,
        *(sorted(sql_root_path.rglob("*.sql")) if sql_root_path.exists() else []),
        *(sorted(scripts_root_path.rglob("*")) if scripts_root_path.exists() else []),
        *(sorted(python_root_path.rglob("*.py")) if python_root_path.exists() else []),
        *instruction_files,
    ]
    checksum_paths = [path for path in checksum_paths if path.is_file()]

    document = _build_content_document(
        report=report,
        query_catalog=query_index,
        script_catalog=script_catalog,
        metric_catalog=metric_catalog,
        python_catalog=python_catalog,
        field_reference_catalog=field_reference_catalog,
        queries=queries,
        scripts=scripts,
        metrics=metrics,
        pythons=pythons,
        sampler_providers=sampler_providers,
        instructions=instructions,
    )
    provenance = _build_content_provenance(
        root=root,
        report_path=report_path,
        query_index_path=query_index_path,
        script_path=script_path,
        metric_path=metric_path,
        python_path=python_path,
        field_reference_path=field_reference_path,
        query_source_files=query_source_files,
        queries=queries,
        scripts=scripts,
        metrics=metrics,
        pythons=pythons,
        sampler_providers=sampler_providers,
        instructions=instructions,
    )

    return ContentPack(
        path=root,
        report=report,
        query_catalog=query_index,
        script_catalog=script_catalog,
        metric_catalog=metric_catalog,
        python_catalog=python_catalog,
        field_reference_catalog=field_reference_catalog,
        instructions=instructions,
        queries=queries,
        scripts=scripts,
        metrics=metrics,
        pythons=pythons,
        sampler_providers=sampler_providers,
        document=document,
        provenance=provenance,
        catalog_files=catalog_files,
        checksum=_content_checksum(checksum_paths, root),
    )


def iter_report_items(content: ContentPack):
    yield from iter_report_items_from_report(content.report)


def iter_report_items_from_report(report: dict[str, Any]):
    sections = report.get("sections") or {}
    if not isinstance(sections, dict):
        return
    for section_id, section in sections.items():
        if not isinstance(section, dict):
            continue
        items = section.get("items") or {}
        if not isinstance(items, dict):
            continue
        for item_key, item in items.items():
            yield section_id, item_key, f"{section_id}.{item_key}", item if isinstance(item, dict) else {}
