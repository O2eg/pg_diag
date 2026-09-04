"""Bounded, deduplicated payload references for server-log event charts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CHART_POINT_LIMIT = 2_000
TEXT_REFERENCE_LIMIT = 1_000
TEXT_REFERENCE_BYTES = 2 * 1_048_576
PLAN_REFERENCE_LIMIT = 256
PLAN_REFERENCE_BYTES = 8 * 1_048_576
MESSAGE_SAMPLE_CHARS = 2_000
QUERY_SAMPLE_CHARS = 300


@dataclass
class ChartReferencePool:
    """Intern chart evidence while enforcing independent text and plan budgets."""

    messages: dict[str, str] = field(default_factory=dict)
    queries: dict[str, str] = field(default_factory=dict)
    plans: dict[str, dict[str, str]] = field(default_factory=dict)
    _message_ids: dict[str, str] = field(default_factory=dict)
    _query_ids: dict[str, str] = field(default_factory=dict)
    _plan_ids: dict[tuple[str, str], str] = field(default_factory=dict)
    _text_bytes: int = 0
    _plan_bytes: int = 0
    omitted_messages: int = 0
    omitted_queries: int = 0
    omitted_plans: int = 0

    def add_message(self, value: str | None) -> str | None:
        return self._add_text(
            value,
            namespace=self.messages,
            reverse=self._message_ids,
            prefix="m",
            max_chars=MESSAGE_SAMPLE_CHARS,
            omitted_attribute="omitted_messages",
        )

    def add_query(self, value: str | None) -> str | None:
        return self._add_text(
            value,
            namespace=self.queries,
            reverse=self._query_ids,
            prefix="q",
            max_chars=QUERY_SAMPLE_CHARS,
            omitted_attribute="omitted_queries",
        )

    def add_plan(self, plan_format: str, value: str | None) -> str | None:
        if not value:
            return None
        key = (plan_format, value)
        existing = self._plan_ids.get(key)
        if existing is not None:
            return existing
        encoded_bytes = len(value.encode("utf-8", "replace")) + len(plan_format) + 32
        if len(self.plans) >= PLAN_REFERENCE_LIMIT or (
            self._plan_bytes + encoded_bytes > PLAN_REFERENCE_BYTES
        ):
            self.omitted_plans += 1
            return None
        reference = f"p{len(self.plans) + 1}"
        self.plans[reference] = {"format": plan_format, "text": value}
        self._plan_ids[key] = reference
        self._plan_bytes += encoded_bytes
        return reference

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.messages:
            result["messages"] = self.messages
        if self.queries:
            result["queries"] = self.queries
        if self.plans:
            result["plans"] = self.plans
        return result

    @property
    def omitted_total(self) -> int:
        return self.omitted_messages + self.omitted_queries + self.omitted_plans

    def _add_text(
        self,
        value: str | None,
        *,
        namespace: dict[str, str],
        reverse: dict[str, str],
        prefix: str,
        max_chars: int,
        omitted_attribute: str,
    ) -> str | None:
        if not value:
            return None
        value = value[:max_chars]
        existing = reverse.get(value)
        if existing is not None:
            return existing
        encoded_bytes = len(value.encode("utf-8", "replace")) + 16
        if (
            len(self.messages) + len(self.queries) >= TEXT_REFERENCE_LIMIT
            or self._text_bytes + encoded_bytes > TEXT_REFERENCE_BYTES
        ):
            setattr(self, omitted_attribute, getattr(self, omitted_attribute) + 1)
            return None
        reference = f"{prefix}{len(namespace) + 1}"
        namespace[reference] = value
        reverse[value] = reference
        self._text_bytes += encoded_bytes
        return reference
