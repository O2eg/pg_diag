"""Build execution plans from declarative content."""

from __future__ import annotations

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
            "collection_scope": self.collection_scope,
            "source_metadata": self.source_metadata,
        }


@dataclass(frozen=True)
class ExecutionPlan:
    mode: str
    collection_mode: str
    server_version_num: int
    supported_server_version: bool
    reason: str | None
    sections: list[dict[str, Any]]
    items: list[PlannedItem]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "collection_mode": self.collection_mode,
            "server_version_num": self.server_version_num,
            "supported_server_version": self.supported_server_version,
            "reason": self.reason,
            "sections": self.sections,
            "items": [item.to_dict() for item in self.items],
        }


def build_plan(
    content: ContentPack,
    server_version_num: int,
    mode: str = runtime_config.SNAPSHOT_MODE,
    collection_mode: str = runtime_config.DEFAULT_COLLECTION_MODE,
) -> ExecutionPlan:
    unsupported_reason = supported_version_reason(server_version_num)
    metric_dependencies = _metric_dependencies(content) if mode == runtime_config.SNAPSHOTS_MODE else set()
    sections = _plan_sections(content)
    items: list[PlannedItem] = []
    report_query_ids: set[str] = set()

    for section_id, item_key, item_id, item in iter_report_items(content):
        source_kind = _source_kind(item)
        if unsupported_reason:
            items.append(
                PlannedItem(
                    item_id=item_id,
                    section_id=section_id,
                    item_key=item_key,
                    title=_item_title(content, source_kind, item, item_key),
                    source_kind=source_kind,
                    source_id=item.get(source_kind),
                    status="unsupported",
                    state=_item_state(item),
                    reason=unsupported_reason,
                )
            )
            continue

        if source_kind == "query":
            report_query_ids.add(item["query"])
            items.append(_plan_query_item(content, section_id, item_key, item_id, item, server_version_num, mode, metric_dependencies))
        elif source_kind == "script":
            items.append(_plan_script_item(content, section_id, item_key, item_id, item, collection_mode))
        elif source_kind == "metric":
            items.append(_plan_metric_item(content, section_id, item_key, item_id, item, mode))
        else:
            items.append(
                PlannedItem(
                    item_id=item_id,
                    section_id=section_id,
                    item_key=item_key,
                    title=item_key,
                    source_kind="unknown",
                    status="error",
                    state=_item_state(item),
                    reason="Cannot determine item source kind",
                )
            )

    if unsupported_reason is None and metric_dependencies:
        for query_id in sorted(metric_dependencies - report_query_ids):
            items.append(
                _plan_hidden_metric_source_query(
                    content,
                    query_id,
                    server_version_num,
                    mode,
                    metric_dependencies,
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
    )


def _source_kind(item: dict[str, Any]) -> str:
    for key in ("query", "script", "metric"):
        if key in item:
            return key
    return "unknown"


def _plan_sections(content: ContentPack) -> list[dict[str, Any]]:
    planned = []
    for section_id, section in (content.report.get("sections") or {}).items():
        item_ids = [f"{section_id}.{item_key}" for item_key in ((section or {}).get("items") or {})]
        planned.append(
            {
                "section_id": section_id,
                "title": section.get("title", section_id),
                "state": section.get("state", (content.report.get("defaults") or {}).get("item", {}).get("state")),
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
    else:
        manifest = {}
    return item.get("title") or manifest.get("title") or item_key


def _item_state(item: dict[str, Any]) -> str | None:
    state = item.get("state")
    return state if state in {"expanded", "collapsed", "hidden"} else None


def _plan_query_item(
    content: ContentPack,
    section_id: str,
    item_key: str,
    item_id: str,
    item: dict[str, Any],
    server_version_num: int,
    mode: str,
    metric_dependencies: set[str],
    internal: bool = False,
) -> PlannedItem:
    query_id = item["query"]
    manifest = content.queries[query_id]
    selection = select_query_variant(query_id, manifest, server_version_num)
    if selection.status != "ok" or selection.variant is None:
        source_metadata = {}
        if internal:
            source_metadata["internal"] = True
        return PlannedItem(
            item_id=item_id,
            section_id=section_id,
            item_key=item_key,
            title=_item_title(content, "query", item, item_key),
            source_kind="query",
            source_id=query_id,
            status="unsupported",
            state=_item_state(item),
            reason=selection.reason,
            source_metadata=source_metadata,
        )

    collection_scope = "once"
    if mode == runtime_config.SNAPSHOTS_MODE:
        collection = manifest.get("collection") or {}
        if collection.get("default") == "every_snapshot" or query_id in metric_dependencies:
            collection_scope = "every_snapshot"
        else:
            collection_scope = "once:latest"

    variant = selection.variant
    source_metadata = {
        "query_id": query_id,
        "variant_id": variant.get("id"),
        "sql_file": variant.get("sql_file"),
        "main_view": manifest.get("main_view"),
        "cost": manifest.get("cost"),
        "display": manifest.get("display") or {},
        "semantic_columns": variant.get("semantic_columns") or {},
    }
    if internal:
        source_metadata["internal"] = True
    return PlannedItem(
        item_id=item_id,
        section_id=section_id,
        item_key=item_key,
        title=_item_title(content, "query", item, item_key),
        source_kind="query",
        source_id=query_id,
        status="planned",
        state=_item_state(item),
        variant_id=variant.get("id"),
        sql_file=variant.get("sql_file"),
        collection_scope=collection_scope,
        source_metadata=source_metadata,
    )


def _plan_hidden_metric_source_query(
    content: ContentPack,
    query_id: str,
    server_version_num: int,
    mode: str,
    metric_dependencies: set[str],
) -> PlannedItem:
    item_key = query_id.replace(".", "_")
    return _plan_query_item(
        content,
        "__metric_sources",
        item_key,
        f"__metric_sources.{item_key}",
        {"query": query_id, "state": "hidden"},
        server_version_num,
        mode,
        metric_dependencies,
        internal=True,
    )


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
    if collection_mode == runtime_config.REMOTE_DB_ONLY_COLLECTION_MODE and script.get("local_only", True):
        message = (content.report.get("runtime_policy") or {}).get(
            "remote_db_only_shell_message", "no data bacause remote call"
        )
        return PlannedItem(
            item_id=item_id,
            section_id=section_id,
            item_key=item_key,
            title=_item_title(content, "script", item, item_key),
            source_kind="script",
            source_id=script_id,
            status="skipped",
            state=_item_state(item),
            reason=message,
            script_file=script.get("script_file"),
            collection_scope="once",
            source_metadata={
                "script_id": script_id,
                "script_file": script.get("script_file"),
                "output": script.get("output"),
            },
        )

    return PlannedItem(
        item_id=item_id,
        section_id=section_id,
        item_key=item_key,
        title=_item_title(content, "script", item, item_key),
        source_kind="script",
        source_id=script_id,
        status="planned",
        state=_item_state(item),
        script_file=script.get("script_file"),
        collection_scope="once",
        source_metadata={
            "script_id": script_id,
            "script_file": script.get("script_file"),
            "output": script.get("output"),
        },
    )


def _plan_metric_item(
    content: ContentPack,
    section_id: str,
    item_key: str,
    item_id: str,
    item: dict[str, Any],
    mode: str,
) -> PlannedItem:
    metric_id = item["metric"]
    metric = content.metrics[metric_id]
    if mode == runtime_config.SNAPSHOT_MODE:
        return PlannedItem(
            item_id=item_id,
            section_id=section_id,
            item_key=item_key,
            title=_item_title(content, "metric", item, item_key),
            source_kind="metric",
            source_id=metric_id,
            status="skipped",
            state=_item_state(item),
            reason="requires snapshots mode",
            source_metadata={
                "metric_id": metric_id,
                "source_query": metric.get("source_query"),
                "source_sampler": metric.get("source_sampler"),
                "chart": metric.get("chart") or {},
                "display": metric.get("display") or {},
            },
        )

    return PlannedItem(
        item_id=item_id,
        section_id=section_id,
        item_key=item_key,
        title=_item_title(content, "metric", item, item_key),
        source_kind="metric",
        source_id=metric_id,
        status="planned",
        state=_item_state(item),
        collection_scope="post_collection",
        source_metadata={
            "metric_id": metric_id,
            "source_query": metric.get("source_query"),
            "source_sampler": metric.get("source_sampler"),
            "chart": metric.get("chart") or {},
            "display": metric.get("display") or {},
        },
    )


def _metric_dependencies(content: ContentPack) -> set[str]:
    return {
        metric.get("source_query")
        for metric in content.metrics.values()
        if metric.get("requires_collection") == "every_snapshot" and metric.get("source_query")
    }
