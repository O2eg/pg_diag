"""One catalog key per PostgreSQL ID, or a text hash when the ID is absent."""
from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from typing import Any


@lru_cache(maxsize=4096)
def query_reference(query: str | None, query_id: Any = None) -> str | None:
    if query_id is not None and str(query_id).strip() not in ("", "0"):
        return str(query_id).strip()
    if not query or not query.strip():
        return None
    return sha256(query.strip().encode("utf-8", "replace")).hexdigest()[:20]


def query_columns(record: Any) -> dict[str, Any]:
    if not record.query and not record.query_id:
        return {}
    identity = query_reference(record.query, record.query_id)
    return {"query_id": identity, "query_ref": identity if record.query else None}


def remember_query(queries: dict, query: str | None, query_id: Any) -> None:
    identity = query_reference(query, query_id)
    if identity:
        # Later records may supply SQL for an ID first encountered without text.
        queries[identity] = queries.get(identity) or (identity if query else None)


def remember_group_query(group: dict, record: Any) -> None:
    remember_query(group.setdefault("queries", {}), record.query, record.query_id)


def group_query_columns(group: dict) -> dict[str, Any]:
    queries = group.get("queries", {})
    if not queries:
        return {}
    if len(queries) == 1:
        query_id, reference = next(iter(queries.items()))
        return {"query_id": query_id, "query_ref": reference}
    return {"query_id": list(queries), "query_ref": list(queries.values())}
