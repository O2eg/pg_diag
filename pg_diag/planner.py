"""Build execution plans from declarative content."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from . import runtime_config
from .content_loader import ContentPack, iter_report_items
from .versioning import select_query_variant, supported_version_reason


@dataclass(frozen=True)
class PlannedItem:
    item_id: str
    section_id: str
    item_key: str
    title: str
    source_kind: str
    status: str
    state: str | None = None
    reason: str | None = None
    source_id: str | None = None
    variant_id: str | None = None
    sql_file: str | None = None
    script_file: str | None = None
    python_file: str | None = None
    collection_scope: str | None = None
    source_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "section_id": self.section_id,
            "item_key": self.item_key,
            "title": self.title,
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "status": self.status,
            "state": self.state,
            "reason": self.reason,
            "variant_id": self.variant_id,
            "sql_file": self.sql_file,
            "script_file": self.script_file,
            "python_file": self.python_file,
            "collection_scope": self.collection_scope,
            "source_metadata": self.source_metadata,
        }


@dataclass(frozen=True)
class SourceJob:
    """Internal collection job that supplies one or more metric report items."""

    job_id: str
    title: str
    source_id: str
    status: str
    reason: str | None = None
    variant_id: str | None = None
    sql_file: str | None = None
    collection_scope: str | None = None
    source_metadata: dict[str, Any] = field(default_factory=dict)

    source_kind: str = field(default="query", init=False)

    @property
    def item_id(self) -> str:
        return self.job_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "status": self.status,
            "reason": self.reason,
            "variant_id": self.variant_id,
            "sql_file": self.sql_file,
            "collection_scope": self.collection_scope,
            "source_metadata": self.source_metadata,
        }


PlannedEntry = PlannedItem | SourceJob


@dataclass(frozen=True)
class ExecutionPlan:
    mode: str
    collection_mode: str
    server_version_num: int
    supported_server_version: bool
    reason: str | None
    sections: list[dict[str, Any]]
    items: list[PlannedItem]
    source_jobs: list[SourceJob]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "collection_mode": self.collection_mode,
            "server_version_num": self.server_version_num,
            "supported_server_version": self.supported_server_version,
            "reason": self.reason,
            "sections": self.sections,
            "items": [item.to_dict() for item in self.items],
            "source_jobs": [job.to_dict() for job in self.source_jobs],
        }


def build_plan(
    content: ContentPack,
    server_version_num: int,
    mode: str = runtime_config.ONE_SHOT_MODE,
    collection_mode: str = runtime_config.DEFAULT_COLLECTION_MODE,
    item_id: str | Iterable[str] | None = None,
    tags: Iterable[str] | None = None,
) -> ExecutionPlan:
    if item_id is not None and tags is not None:
        raise ValueError("--item-id and --tags cannot be used together")
    requested_item_ids = normalize_requested_item_ids(content, item_id)
    requested_tags = normalize_requested_tags(content, tags)
    selected_item_ids = _selected_report_item_ids(content, requested_item_ids, requested_tags)
    unsupported_reason = supported_version_reason(server_version_num)
    metric_dependencies = (
        _metric_dependencies(content, selected_item_ids=selected_item_ids)
        if mode == runtime_config.SNAPSHOTS_MODE
        else {}
    )
    query_usage_index = _query_usage_index(content)
    sections = _plan_sections(content)
    items: list[PlannedItem] = []
    source_jobs: list[SourceJob] = []

    for section_id, item_key, iter_item_id, item in iter_report_items(content):
        planned_item_id = f"{section_id}.{item_key}"
        if selected_item_ids is not None and planned_item_id not in selected_item_ids:
            continue
        source_kind = _source_kind(item)
        if unsupported_reason:
            items.append(
                PlannedItem(
                    item_id=planned_item_id,
                    section_id=section_id,
                    item_key=item_key,
                    title=_item_title(content, source_kind, item, item_key),
                    source_kind=source_kind,
                    source_id=item.get(source_kind),
                    status="unsupported",
                    state=_item_state(content, item),
                    reason=unsupported_reason,
                    source_metadata=_with_item_metadata(content, planned_item_id, item),
                )
            )
            continue

        if source_kind == "query":
            items.append(
                _plan_query_item(
                    content,
                    section_id,
                    item_key,
                    planned_item_id,
                    item,
                    server_version_num,
                    query_usage_index,
                )
            )
        elif source_kind == "script":
            items.append(_plan_script_item(content, section_id, item_key, planned_item_id, item, collection_mode))
        elif source_kind == "python":
            items.append(_plan_python_item(content, section_id, item_key, planned_item_id, item, collection_mode))
        elif source_kind == "metric":
            items.append(
                _plan_metric_item(
                    content,
                    section_id,
                    item_key,
                    planned_item_id,
                    item,
                    mode,
                    collection_mode,
                    query_usage_index,
                )
            )
        else:
            raise ValueError(f"Unsupported source kind {source_kind!r} for item {planned_item_id}")

    planned_item_ids = {item.item_id for item in items}
    sections = [
        {
            **section,
            "items": [iid for iid in section["items"] if iid in planned_item_ids],
        }
        for section in sections
        if any(iid in planned_item_ids for iid in section["items"])
    ]

    if unsupported_reason is None and metric_dependencies:
        for query_id in sorted(metric_dependencies):
            source_jobs.append(
                _plan_metric_source_job(
                    content,
                    query_id,
                    server_version_num,
                    metric_dependencies,
                    query_usage_index,
                )
            )

    return ExecutionPlan(
        mode=mode,
        collection_mode=collection_mode,
        server_version_num=server_version_num,
        supported_server_version=unsupported_reason is None,
        reason=unsupported_reason,
        sections=sections,
        items=items,
        source_jobs=source_jobs,
    )


def available_report_item_ids(content: ContentPack) -> list[str]:
    """Return report item ids in their declared display order."""
    return [item_id for _section_id, _item_key, item_id, _item in iter_report_items(content)]


def normalize_requested_item_ids(
    content: ContentPack,
    item_id: str | Iterable[str] | None,
) -> tuple[str, ...] | None:
    """Validate and de-duplicate a scalar or list report-item filter."""
    if item_id is None:
        return None
    values = [item_id] if isinstance(item_id, str) else list(item_id)
    if not values:
        raise ValueError("--item-id requires at least one report item")

    available = set(available_report_item_ids(content))
    normalized: list[str] = []
    unknown: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text not in available:
            unknown.append(text or "<empty>")
            continue
        if text not in seen:
            normalized.append(text)
            seen.add(text)
    if unknown:
        if len(unknown) == 1:
            raise ValueError(f"Unknown report item: {unknown[0]}")
        raise ValueError(f"Unknown report items: {', '.join(unknown)}")
    return tuple(normalized)


def validate_requested_item_id(
    content: ContentPack,
    item_id: str | Iterable[str] | None,
) -> None:
    """Backward-compatible validation wrapper for report item filters."""
    normalize_requested_item_ids(content, item_id)


def available_item_tags(content: ContentPack) -> list[str]:
    """Return canonical tags which are assigned to at least one report item."""
    used = {
        tag
        for _section_id, _item_key, _item_id, item in iter_report_items(content)
        for tag in _item_tags(item)
    }
    declared = list((content.report.get("report") or {}).get("allowed_item_tags") or [])
    ordered = [str(tag) for tag in declared if str(tag) in used]
    declared_set = set(ordered)
    ordered.extend(sorted(used.difference(declared_set), key=str.casefold))
    return ordered


def normalize_requested_tags(
    content: ContentPack,
    tags: Iterable[str] | None,
) -> tuple[str, ...] | None:
    """Resolve a case-insensitive tag filter to canonical content tag names."""
    if tags is None:
        return None
    values = [tags] if isinstance(tags, str) else list(tags)
    if not values:
        raise ValueError("--tags requires at least one report tag")

    canonical_by_folded = {
        tag.casefold(): tag
        for tag in available_item_tags(content)
    }
    normalized: list[str] = []
    unknown: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        canonical = canonical_by_folded.get(text.casefold()) if text else None
        if canonical is None:
            unknown.append(text or "<empty>")
            continue
        if canonical not in seen:
            normalized.append(canonical)
            seen.add(canonical)
    if unknown:
        available = ", ".join(available_item_tags(content))
        raise ValueError(
            f"Unknown report tag(s): {', '.join(unknown)}. Available tags: {available}"
        )
    return tuple(normalized)


def _selected_report_item_ids(
    content: ContentPack,
    item_ids: tuple[str, ...] | None,
    tags: tuple[str, ...] | None,
) -> set[str] | None:
    if item_ids is not None:
        return set(item_ids)
    if tags is None:
        return None
    requested = set(tags)
    return {
        report_item_id
        for _section_id, _item_key, report_item_id, item in iter_report_items(content)
        if requested.intersection(_item_tags(item))
    }


def _source_kind(item: dict[str, Any]) -> str:
    source_kinds = [key for key in ("query", "script", "metric", "python") if key in item]
    if len(source_kinds) != 1:
        raise ValueError("Report item must declare exactly one source kind")
    return source_kinds[0]


def _plan_sections(content: ContentPack) -> list[dict[str, Any]]:
    planned = []
    for section_id, section in (content.report.get("sections") or {}).items():
        item_ids = [
            f"{section_id}.{item_key}"
            for item_key, item in ((section or {}).get("items") or {}).items()
            if _item_state(content, item or {}) != "hidden"
        ]
        planned.append(
            {
                "section_id": section_id,
                "title": section.get("title", section_id),
                "state": _section_state(content, section),
                "items": item_ids,
            }
        )
    return planned


def _item_title(content: ContentPack, source_kind: str, item: dict[str, Any], item_key: str) -> str:
    if source_kind == "query":
        manifest = content.queries.get(item.get("query"), {})
    elif source_kind == "script":
        manifest = content.scripts.get(item.get("script"), {})
    elif source_kind == "metric":
        manifest = content.metrics.get(item.get("metric"), {})
    elif source_kind == "python":
        manifest = content.pythons.get(item.get("python"), {})
    else:
        manifest = {}
    return item["title"] if "title" in item else manifest["title"]


def _item_state(content: ContentPack, item: dict[str, Any]) -> str:
    state = item.get("state")
    if state in {"expanded", "collapsed", "hidden"}:
        return state
    return content.report["defaults"]["item"]["state"]


def _section_state(content: ContentPack, section: dict[str, Any]) -> str:
    state = section.get("state")
    if state in {"expanded", "collapsed", "hidden"}:
        return state
    return content.report["defaults"]["section"]["state"]


def _with_item_metadata(
    content: ContentPack,
    item_id: str,
    item: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = dict(metadata or {})
    database_scope = _item_database_scope(content, item_id, item, result)
    if database_scope is None:
        result.pop("database_scope", None)
    else:
        result["database_scope"] = database_scope
    tags = _item_tags(item)
    if tags:
        result["tags"] = tags
    render = item.get("render")
    if isinstance(render, dict):
        result["render"] = dict(render)
    instruction = content.instructions.get(item_id)
    if instruction:
        result["instructions"] = instruction
    return result


def _item_database_scope(
    content: ContentPack,
    item_id: str,
    item: dict[str, Any],
    metadata: dict[str, Any],
) -> str | None:
    section_id = item_id.partition(".")[0]
    section = (content.report.get("sections") or {}).get(section_id) or {}
    if section.get("show_database_scope") is False:
        return None

    scope = item.get("database_scope") or metadata.get("database_scope")
    if scope is None:
        source_kind = _source_kind(item)
        source_id = item.get(source_kind)
        catalogs = {
            "query": content.queries,
            "script": content.scripts,
            "metric": content.metrics,
            "python": content.pythons,
        }
        scope = (catalogs.get(source_kind, {}).get(source_id) or {}).get("database_scope")
    if scope is None:
        defaults = content.report.get("defaults") or {}
        scope = (defaults.get("item") or {}).get("database_scope")
    return str(scope) if scope is not None else None


def _item_tags(item: dict[str, Any]) -> list[str]:
    tags = item.get("tags") or []
    if not isinstance(tags, list):
        return []
    normalized = []
    seen = set()
    for tag in tags:
        text = str(tag).strip()
        if text and text not in seen:
            normalized.append(text)
            seen.add(text)
    return normalized


def _query_usage_index(content: ContentPack) -> dict[str, list[str]]:
    usage: dict[str, list[str]] = {}
    for _section_id, _item_key, item_id, item in iter_report_items(content):
        query_id = _sql_source_query_id(content, item)
        if not query_id:
            continue
        usage.setdefault(query_id, []).append(item_id)
    return usage


def _sql_source_query_id(content: ContentPack, item: dict[str, Any]) -> str | None:
    if "query" in item:
        return item["query"]
    if "metric" in item:
        metric = content.metrics[item["metric"]]
        return metric.get("source_query")
    return None


def _query_usage_metadata(query_id: str, item_id: str, query_usage_index: dict[str, list[str]]) -> dict[str, Any]:
    item_ids = list(query_usage_index[query_id])
    other_item_ids = [used_item_id for used_item_id in item_ids if used_item_id != item_id]
    return {
        "query_usage": {
            "query_id": query_id,
            "isolation": "isolated" if len(item_ids) <= 1 else "shared",
            "item_count": len(item_ids),
            "item_ids": item_ids,
            "other_item_ids": other_item_ids,
        }
    }


def _plan_query_item(
    content: ContentPack,
    section_id: str,
    item_key: str,
    item_id: str,
    item: dict[str, Any],
    server_version_num: int,
    query_usage_index: dict[str, list[str]],
) -> PlannedItem:
    query_id = item["query"]
    manifest = content.queries[query_id]
    selection = select_query_variant(query_id, manifest, server_version_num)
    if selection.status != "ok" or selection.variant is None:
        source_metadata = {
            "database_scope": manifest.get("database_scope"),
            **_query_usage_metadata(query_id, item_id, query_usage_index),
        }
        return PlannedItem(
            item_id=item_id,
            section_id=section_id,
            item_key=item_key,
            title=_item_title(content, "query", item, item_key),
            source_kind="query",
            source_id=query_id,
            status="unsupported",
            state=_item_state(content, item),
            reason=selection.reason,
            source_metadata=_with_item_metadata(content, item_id, item, source_metadata),
        )

    variant = selection.variant
    source_metadata = _query_source_metadata(
        manifest,
        variant,
        _query_usage_metadata(query_id, item_id, query_usage_index),
    )
    source_metadata = _with_item_metadata(content, item_id, item, source_metadata)
    return PlannedItem(
        item_id=item_id,
        section_id=section_id,
        item_key=item_key,
        title=_item_title(content, "query", item, item_key),
        source_kind="query",
        source_id=query_id,
        status="planned",
        state=_item_state(content, item),
        variant_id=variant.get("id"),
        sql_file=variant.get("sql_file"),
        collection_scope=runtime_config.ONCE_COLLECTION_SCOPE,
        source_metadata=source_metadata,
    )


def _plan_metric_source_job(
    content: ContentPack,
    query_id: str,
    server_version_num: int,
    metric_dependencies: dict[str, str],
    query_usage_index: dict[str, list[str]],
) -> SourceJob:
    manifest = content.queries[query_id]
    selection = select_query_variant(query_id, manifest, server_version_num)
    collection_scope = metric_dependencies[query_id]
    consumers = query_usage_index[query_id]
    usage = _query_usage_metadata(query_id, consumers[0], query_usage_index)
    if selection.status != "ok" or selection.variant is None:
        return SourceJob(
            job_id=query_id,
            title=manifest["title"],
            source_id=query_id,
            status="unsupported",
            reason=selection.reason,
            collection_scope=collection_scope,
            source_metadata=usage,
        )

    variant = selection.variant
    return SourceJob(
        job_id=query_id,
        title=manifest["title"],
        source_id=query_id,
        status="planned",
        variant_id=variant.get("id"),
        sql_file=variant.get("sql_file"),
        collection_scope=collection_scope,
        source_metadata=_query_source_metadata(manifest, variant, usage),
    )


def _query_source_metadata(
    manifest: dict[str, Any],
    variant: dict[str, Any],
    usage: dict[str, Any],
) -> dict[str, Any]:
    return {
        "query_id": usage["query_usage"]["query_id"],
        "variant_id": variant.get("id"),
        "sql_file": variant.get("sql_file"),
        "main_view": manifest.get("main_view"),
        "cost": manifest.get("cost"),
        "source": manifest.get("source"),
        "optional": bool(manifest.get("optional")),
        "display": manifest.get("display") or {},
        "evaluation": manifest.get("evaluation") or {},
        "database_scope": manifest.get("database_scope"),
        "semantic_columns": variant.get("semantic_columns") or {},
        "column_statuses": variant.get("column_statuses") or {},
        **usage,
    }


def _plan_script_item(
    content: ContentPack,
    section_id: str,
    item_key: str,
    item_id: str,
    item: dict[str, Any],
    collection_mode: str,
) -> PlannedItem:
    script_id = item["script"]
    script = content.scripts[script_id]
    if collection_mode == runtime_config.REMOTE_DB_ONLY_COLLECTION_MODE and script["local_only"]:
        message = _remote_script_message(content, script)
        return PlannedItem(
            item_id=item_id,
            section_id=section_id,
            item_key=item_key,
            title=_item_title(content, "script", item, item_key),
            source_kind="script",
            source_id=script_id,
            status="skipped",
            state=_item_state(content, item),
            reason=message,
            script_file=script.get("script_file"),
            collection_scope="once",
            source_metadata=_with_item_metadata(content, item_id, item, {
                "script_id": script_id,
                "script_file": script.get("script_file"),
                "output": script.get("output"),
                "remote_message": message,
            }),
        )

    source_metadata = _with_item_metadata(content, item_id, item, {
        "script_id": script_id,
        "script_file": script.get("script_file"),
        "output": script.get("output"),
    })
    return PlannedItem(
        item_id=item_id,
        section_id=section_id,
        item_key=item_key,
        title=_item_title(content, "script", item, item_key),
        source_kind="script",
        source_id=script_id,
        status="planned",
        state=_item_state(content, item),
        script_file=script.get("script_file"),
        collection_scope="once",
        source_metadata=source_metadata,
    )


def _plan_python_item(
    content: ContentPack,
    section_id: str,
    item_key: str,
    item_id: str,
    item: dict[str, Any],
    collection_mode: str,
) -> PlannedItem:
    python_id = item["python"]
    python_source = content.pythons[python_id]
    if collection_mode == runtime_config.REMOTE_DB_ONLY_COLLECTION_MODE and python_source["local_only"]:
        message = content.report["runtime_policy"]["remote_db_only_shell_message"]
        return PlannedItem(
            item_id=item_id,
            section_id=section_id,
            item_key=item_key,
            title=_item_title(content, "python", item, item_key),
            source_kind="python",
            source_id=python_id,
            status="skipped",
            state=_item_state(content, item),
            reason=message,
            python_file=python_source.get("python_file"),
            collection_scope="once",
            source_metadata=_with_item_metadata(content, item_id, item, {
                "python_id": python_id,
                "python_file": python_source.get("python_file"),
                "function": python_source.get("function"),
                "display": python_source.get("display") or {},
                "remote_message": message,
            }),
        )

    source_metadata = _with_item_metadata(content, item_id, item, {
        "python_id": python_id,
        "python_file": python_source.get("python_file"),
        "function": python_source.get("function"),
        "display": python_source.get("display") or {},
    })
    return PlannedItem(
        item_id=item_id,
        section_id=section_id,
        item_key=item_key,
        title=_item_title(content, "python", item, item_key),
        source_kind="python",
        source_id=python_id,
        status="planned",
        state=_item_state(content, item),
        python_file=python_source.get("python_file"),
        collection_scope="once",
        source_metadata=source_metadata,
    )


def _plan_metric_item(
    content: ContentPack,
    section_id: str,
    item_key: str,
    item_id: str,
    item: dict[str, Any],
    mode: str,
    collection_mode: str,
    query_usage_index: dict[str, list[str]],
) -> PlannedItem:
    metric_id = item["metric"]
    metric = content.metrics[metric_id]
    source_query = metric.get("source_query")
    query_usage_metadata = _query_usage_metadata(source_query, item_id, query_usage_index) if source_query else {}
    if mode == runtime_config.ONE_SHOT_MODE:
        return PlannedItem(
            item_id=item_id,
            section_id=section_id,
            item_key=item_key,
            title=_item_title(content, "metric", item, item_key),
            source_kind="metric",
            source_id=metric_id,
            status="skipped",
            state=_item_state(content, item),
            reason="requires snapshots mode",
            source_metadata=_with_item_metadata(content, item_id, item, {
                "metric_id": metric_id,
                "source_query": source_query,
                "source_sampler": metric.get("source_sampler"),
                "database_scope": metric.get("database_scope"),
                "chart": metric.get("chart") or {},
                "display": metric.get("display") or {},
                **query_usage_metadata,
            }),
        )

    if (
        collection_mode == runtime_config.REMOTE_DB_ONLY_COLLECTION_MODE
        and metric.get("source_sampler")
    ):
        return PlannedItem(
            item_id=item_id,
            section_id=section_id,
            item_key=item_key,
            title=_item_title(content, "metric", item, item_key),
            source_kind="metric",
            source_id=metric_id,
            status="skipped",
            state=_item_state(content, item),
            reason="remote_db_only",
            source_metadata=_with_item_metadata(content, item_id, item, {
                "metric_id": metric_id,
                "source_sampler": metric.get("source_sampler"),
                "database_scope": metric.get("database_scope"),
                "chart": metric.get("chart") or {},
                "display": metric.get("display") or {},
            }),
        )

    source_metadata = _with_item_metadata(content, item_id, item, {
        "metric_id": metric_id,
        "source_query": source_query,
        "source_sampler": metric.get("source_sampler"),
        "database_scope": metric.get("database_scope"),
        "chart": metric.get("chart") or {},
        "display": metric.get("display") or {},
        **query_usage_metadata,
    })
    return PlannedItem(
        item_id=item_id,
        section_id=section_id,
        item_key=item_key,
        title=_item_title(content, "metric", item, item_key),
        source_kind="metric",
        source_id=metric_id,
        status="planned",
        state=_item_state(content, item),
        collection_scope="post_collection",
        source_metadata=source_metadata,
    )


def _metric_dependencies(
    content: ContentPack,
    selected_item_ids: set[str] | None = None,
) -> dict[str, str]:
    referenced_metric_ids = {
        item.get("metric")
        for _section_id, _item_key, _item_id, item in iter_report_items(content)
        if item.get("metric")
        and (selected_item_ids is None or _item_id in selected_item_ids)
    }
    return {
        str(metric["source_query"]): str(metric["requires_collection"])
        for metric_id, metric in content.metrics.items()
        if metric_id in referenced_metric_ids
        if metric.get("requires_collection") in {
            runtime_config.EVERY_SNAPSHOT_COLLECTION_SCOPE,
            runtime_config.WINDOW_ENDPOINTS_COLLECTION_SCOPE,
        }
        and metric.get("source_query")
    }


def _remote_script_message(content: ContentPack, script: dict[str, Any]) -> str:
    message_ref = script["remote_db_only_behavior"]["message_ref"]
    policy_key = message_ref.split(".", 1)[1]
    return content.report["runtime_policy"][policy_key]
