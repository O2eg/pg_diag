"""Incremental memory accounting for string values retained in log results."""

from __future__ import annotations

import sys
from typing import Any, Iterator

from .model import REASON_VALUE_LIMIT


class LogValueBudget:
    """Count actual string objects, excluding keys and container overhead.

    References to the same object share its cost. Equal but independently
    allocated strings do not. Removing the last retained reference refunds it.
    """

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0
        self._values: dict[int, tuple[str, int]] = {}
        self.query_refs: set[str] = set()
        self.hit = False

    @property
    def reached(self) -> bool:
        return self.used >= self.limit

    def add(self, value: Any) -> None:
        for text in _strings(value):
            identity = id(text)
            previous = self._values.get(identity)
            if previous is None:
                self._values[identity] = (text, 1)
                self.used += sys.getsizeof(text)
            else:
                self._values[identity] = (text, previous[1] + 1)

    def remove(self, value: Any) -> None:
        for text in _strings(value):
            identity = id(text)
            previous = self._values[identity]
            if previous[1] == 1:
                self.used -= sys.getsizeof(previous[0])
                del self._values[identity]
            else:
                self._values[identity] = (previous[0], previous[1] - 1)

    def replace(self, old: Any, new: Any) -> None:
        self.remove(old)
        self.add(new)


def _strings(value: Any) -> Iterator[str]:
    # An explicit stack also supports deeply nested results. Containers are
    # traversed once per operation, so aliases and cycles cannot expand work.
    pending = [value]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if isinstance(current, str):
            yield current
        elif isinstance(current, (dict, list, tuple)) and id(current) not in seen:
            seen.add(id(current))
            pending.extend(current.values() if isinstance(current, dict) else current)


def _references(value: Any) -> Iterator[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"query_ref", "message_ref", "plan_ref"}:
                yield from ((key, text) for text in _strings(child))
            else:
                yield from _references(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _references(child)


def retain_log_item(
    item: dict[str, Any],
    budget: LogValueBudget,
    catalog: dict[str, str],
    query_pool: dict[str, str],
    query_metadata: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    """Retain whole rows/points and their dependencies up to a soft boundary.

    Item sources have already applied their ranking/eviction policies. Only
    their final output enters the report budget; parser records never do.
    """
    if budget.hit:
        item.update(
            collection_status="skipped",
            result={"kind": "none"},
            reason="Log report value budget reached",
            issues={},
            diagnostics=[
                {
                    "level": "warning",
                    "code": REASON_VALUE_LIMIT,
                    "message": "Log report value budget reached",
                }
            ],
        )
        return
    if item.get("collection_status") not in {"ok", "empty"}:
        return
    result = item.get("result") or {}
    references = result.pop("references", {})
    units: list[tuple[list, Any, dict[str, Any]]] = []
    if result.get("kind") == "table":
        rows = result.get("rows", [])
        links = result.get("query_links", {})
        result["rows"] = []
        if links:
            result["query_links"] = {key: [] for key in links}
        units = [
            (
                result["rows"],
                row,
                {
                    key: values[index] if index < len(values) else None
                    for key, values in links.items()
                },
            )
            for index, row in enumerate(rows)
        ]
    elif result.get("kind") == "chart":
        for series in result.get("series", []):
            points = series.get("points", [])
            series["points"] = []
            units.extend((series["points"], point, {}) for point in points)
    if references:
        result["references"] = {}
    # Column descriptors, chart configuration and aggregate metadata are not
    # log payload. Only retained rows/points, references and SQL are charged.
    if not units:
        budget.add(log_payloads(result))
    retained = 0
    for target, unit, links in units:
        # A record and its SQL/plan remain atomic at the crossing boundary.
        if retained and budget.reached:
            break
        dependencies = list(_references(unit))
        dependencies.extend(("query_ref", text) for text in _strings(links))
        for kind, reference in dependencies:
            namespace = {"message_ref": "messages", "plan_ref": "plans", "query_ref": "queries"}[
                kind
            ]
            source = references.get(namespace, {})
            if reference in source:
                destination = result.setdefault("references", {}).setdefault(namespace, {})
                if reference not in destination:
                    destination[reference] = source[reference]
                    budget.add(source[reference])
            elif kind == "query_ref" and reference not in budget.query_refs:
                text = catalog.get(reference, query_pool.get(reference))
                if text is not None:
                    existing = reference in catalog
                    catalog.setdefault(reference, text)
                    budget.query_refs.add(reference)
                    budget.add(catalog[reference])
                    if not existing and reference in query_metadata:
                        metadata.setdefault(reference, query_metadata[reference])
                    if (
                        existing
                        and reference in query_pool
                        and catalog[reference] != query_pool[reference]
                    ):
                        metadata.setdefault(reference, {})["representative_sample"] = True
        target.append(unit)
        budget.add(unit)
        for key, value in links.items():
            result["query_links"][key].append(value)
            budget.add(value)
        retained += 1
    if budget.reached:
        budget.hit = True
    if retained < len(units):
        _mark_item_partial(item, len(units), retained)


def _mark_item_partial(item: dict[str, Any], total: int, retained: int) -> None:
    result = item["result"]
    result["report_value_limit_hit"] = True
    result["budget_omitted_count"] = total - retained
    result["count_complete"] = False
    if result.get("kind") == "table":
        columns = [c if isinstance(c, str) else c.get("name") for c in result.get("columns", [])]
        rows = result["rows"]
        result["row_count"] = len(rows)
        if "count_complete" in columns:
            index = columns.index("count_complete")
            for row in rows:
                if index < len(row):
                    row[index] = False
        count_index = next(
            (columns.index(key) for key in ("repeat_count", "occurrences") if key in columns), None
        )
        events = sum(row[count_index] for row in rows) if count_index is not None else retained
        for key in ("displayed_series_count",):
            if key in result:
                result[key] = retained
        for key in ("omitted_series_count", "omitted_aggregate_count"):
            if key in result:
                result[key] += total - retained
    else:
        points = [p for series in result.get("series", []) for p in series.get("points", [])]
        events = sum(p.get("value", 0) for p in points)
        for key in ("display_point_count", "displayed_point_count", "displayed_plan_count"):
            if key in result:
                result[key] = retained
        for key in ("omitted_point_count", "omitted_plan_count", "bucket_omitted_plan_count"):
            if key in result:
                result[key] += total - retained
    if "displayed_event_count" in result:
        result["omitted_event_count"] += result["displayed_event_count"] - events
        result["displayed_event_count"] = events
    item["reason"] = "Log report value budget reached; output is incomplete"
    item["issues"] = {
        "summary": {
            "severity": "unknown",
            "status": "review",
            "title": "Log output is incomplete",
            "description": f"The report value budget retained {retained} of {total} output records.",
            "recommendation": "Collect a smaller log window to inspect the remaining evidence.",
        },
        "items": [],
    }
    item.setdefault("diagnostics", []).append(
        {
            "level": "warning",
            "code": REASON_VALUE_LIMIT,
            "message": item["reason"],
        }
    )


def update_coverage(artifact: dict[str, Any], budget: LogValueBudget) -> None:
    coverage = (artifact.get("runtime", {}).get("log_collection") or {}).get("coverage")
    if not isinstance(coverage, dict):
        return
    coverage.update(
        estimated_value_bytes=budget.used,
        value_budget_bytes=budget.limit,
        value_budget_method="python_string_objects",
    )
    if budget.hit:
        coverage["truncation_reasons"] = sorted(
            set(coverage.get("truncation_reasons", [])) | {REASON_VALUE_LIMIT}
        )
        coverage.update(window_truncated=True, ranking_complete=False)


def log_payloads(result: dict[str, Any]) -> list[Any]:
    """Roots of retained log data; presentation descriptors are excluded."""
    return [
        result.get("rows", []),
        result.get("query_links", {}),
        result.get("references", {}),
        result.get("data"),
        *[series.get("points", []) for series in result.get("series", [])],
    ]


def finish_budget(artifact: dict[str, Any], budget: LogValueBudget) -> None:
    """One final linear check after presentation has normalized value types.

    Regular admission is incremental. This traversal handles replaced strings
    (timestamps/large integers) without serializing any part of the report.
    """
    measured = LogValueBudget(budget.limit)
    for item_id, item in artifact.get("items", {}).items():
        if item_id.startswith("server_log.") and item.get("collection_status") in {"ok", "empty"}:
            measured.add(log_payloads(item.get("result") or {}))
    for reference in budget.query_refs:
        measured.add(artifact.get("query_texts", {}).get(reference))
    measured.hit = budget.hit
    update_coverage(artifact, measured)
