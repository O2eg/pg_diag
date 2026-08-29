"""Collect DDL for object oids referenced by report items.

After all items are collected, the oid values found in allowlisted oid
columns are deduplicated in memory and their DDL is extracted in a few
batched calls through :mod:`pg_diag.ddlx`.  Both regular item results and
snapshot rows (via ``snapshot_schemas``) are scanned.  The result is
stored in the artifact as the ``object_ddl`` map (``oid -> {kind,
identifier, ddl}``) that the report template uses to make oid cells
clickable, the same way ``query_texts`` backs clickable query ids.

The column allowlist below must stay in sync with
``OBJECT_OID_COLUMN_SUFFIXES`` / ``OBJECT_OID_COLUMN_NAMES`` in
``render/templates/report.html``.
"""

from __future__ import annotations

from typing import Any

from pg_diag.ddlx import DdlExtractor, TableBundle
from pg_diag.security import REDACTED, is_sensitive_name

RELATION_OID_SUFFIXES = ("table_oid", "relation_oid", "index_oid", "sequence_oid")
RELATION_OID_NAMES = ("relid", "indexrelid")
FUNCTION_OID_SUFFIXES = ("function_oid",)
FUNCTION_OID_NAMES = ("funcid",)
CONSTRAINT_OID_SUFFIXES = ("constraint_oid",)
TRIGGER_OID_SUFFIXES = ("trigger_oid",)
DATABASE_OID_SUFFIXES = ("database_oid",)
DATABASE_OID_NAMES = ("datid", "dbid")
ROLE_OID_SUFFIXES = ("role_oid", "owner_oid", "grantee_oid")
ROLE_OID_NAMES = ("userid", "usesysid")
TABLESPACE_OID_SUFFIXES = ("tablespace_oid",)

MAX_RELATIONS = 400
MAX_FUNCTIONS = 200
MAX_CONSTRAINTS = 200
MAX_TRIGGERS = 200
MAX_DATABASES = 50
MAX_ROLES = 200
MAX_TABLESPACES = 20
MAX_DDL_CHARS = 100_000
TRUNCATION_MARKER = "\n-- [pg_diag] DDL truncated"

_EMPTY_KINDS = (
    "relation", "function", "constraint", "trigger", "database", "role", "tablespace"
)


def _column_name(column: Any, index: int) -> str:
    if isinstance(column, str):
        return column
    if isinstance(column, dict):
        return str(column.get("name") or f"column_{index + 1}")
    return f"column_{index + 1}"


def _column_kind(name: str) -> str | None:
    if name in RELATION_OID_NAMES or name.endswith(RELATION_OID_SUFFIXES):
        return "relation"
    if name in FUNCTION_OID_NAMES or name.endswith(FUNCTION_OID_SUFFIXES):
        return "function"
    if name.endswith(CONSTRAINT_OID_SUFFIXES):
        return "constraint"
    if name.endswith(TRIGGER_OID_SUFFIXES):
        return "trigger"
    if name in DATABASE_OID_NAMES or name.endswith(DATABASE_OID_SUFFIXES):
        return "database"
    if name in ROLE_OID_NAMES or name.endswith(ROLE_OID_SUFFIXES):
        return "role"
    if name.endswith(TABLESPACE_OID_SUFFIXES):
        return "tablespace"
    return None


def _remember_oid(bucket: set[int], value: Any) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        oid = value
    elif isinstance(value, str) and value.strip().isdigit():
        oid = int(value.strip())
    else:
        return
    if oid > 0:
        bucket.add(oid)


def _harvest_table(result: Any, columns: Any, harvested: dict[str, set[int]]) -> None:
    rows = (result or {}).get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        return
    oid_columns = []
    for index, column in enumerate(columns):
        kind = _column_kind(_column_name(column, index))
        if kind is not None:
            oid_columns.append((index, kind))
    if not oid_columns:
        return
    for row in rows:
        if not isinstance(row, list):
            continue
        for index, kind in oid_columns:
            if index < len(row):
                _remember_oid(harvested[kind], row[index])


def harvest_object_oids(artifact: dict[str, Any]) -> dict[str, set[int]]:
    """Collect unique object oids from allowlisted columns of all table rows."""
    harvested: dict[str, set[int]] = {kind: set() for kind in _EMPTY_KINDS}
    for item in (artifact.get("items") or {}).values():
        result = (item or {}).get("result") or {}
        if result.get("kind") == "table":
            _harvest_table(result, result.get("columns"), harvested)
    schemas = artifact.get("snapshot_schemas") or {}
    for snapshot in artifact.get("snapshots") or []:
        if not isinstance(snapshot, dict):
            continue
        for source_id, entry in (snapshot.get("items") or {}).items():
            result = (entry or {}).get("result") or {}
            if result.get("kind") != "table":
                continue
            columns = (schemas.get(source_id) or {}).get("columns")
            _harvest_table(result, columns, harvested)
    return harvested


_FUNCTION_KINDS = ("function", "procedure", "window function")


def redact_function_ddl(text: str) -> str:
    """Line-level redaction of function source, matching redact_text semantics.

    Lines that already carry the structural [REDACTED] marker are kept as-is.
    """
    lines = []
    for line in text.splitlines():
        if REDACTED not in line and is_sensitive_name(line):
            lines.append(REDACTED)
        else:
            lines.append(line)
    return "\n".join(lines)


def _entry(kind: str, identifier: str, ddl: str) -> dict[str, str]:
    if kind in _FUNCTION_KINDS:
        ddl = redact_function_ddl(ddl)
    if len(ddl) > MAX_DDL_CHARS:
        ddl = ddl[:MAX_DDL_CHARS] + TRUNCATION_MARKER
    return {"kind": kind, "identifier": identifier, "ddl": ddl}


def bundle_document(bundle: TableBundle) -> str:
    """The pgAdmin-style single document: table, indexes, functions, triggers.

    Trigger functions come before the triggers that call them so the
    document replays on an empty schema.
    """
    parts = [bundle.table.ddl]
    parts.extend(index.ddl for index in bundle.indexes)
    parts.extend(
        redact_function_ddl(function.ddl)
        for function in bundle.trigger_functions
        if function.ddl
    )
    parts.extend(trigger.ddl for trigger in bundle.triggers)
    return "\n\n".join(part for part in parts if part)


def _remember_entries(
    catalog: dict[str, dict[str, str]], objects: dict[int, Any]
) -> None:
    for oid, obj in objects.items():
        if obj.ddl:
            catalog[str(oid)] = _entry(obj.kind, obj.identifier, obj.ddl)


async def collect_object_ddl(
    conn: Any,
    server_version_num: int,
    artifact: dict[str, Any],
) -> dict[str, dict[str, str]]:
    """Extract DDL for every harvested oid; a few batched round trips total."""
    harvested = harvest_object_oids(artifact)
    relation_oids = sorted(harvested["relation"])[:MAX_RELATIONS]
    function_oids = sorted(harvested["function"])[:MAX_FUNCTIONS]
    constraint_oids = sorted(harvested["constraint"])[:MAX_CONSTRAINTS]
    trigger_oids = sorted(harvested["trigger"])[:MAX_TRIGGERS]
    database_oids = sorted(harvested["database"])[:MAX_DATABASES]
    role_oids = sorted(harvested["role"])[:MAX_ROLES]
    tablespace_oids = sorted(harvested["tablespace"])[:MAX_TABLESPACES]
    catalog: dict[str, dict[str, str]] = {}
    if not any(
        (
            relation_oids,
            function_oids,
            constraint_oids,
            trigger_oids,
            database_oids,
            role_oids,
            tablespace_oids,
        )
    ):
        return catalog

    ddlx = DdlExtractor(conn, server_version_num)
    bundles = await ddlx.tables_bundle(relation_oids)
    for oid, bundle in bundles.items():
        document = bundle_document(bundle)
        if document:
            catalog[str(oid)] = _entry(
                bundle.table.kind, bundle.table.identifier, document
            )
    other_relations = [oid for oid in relation_oids if oid not in bundles]
    _remember_entries(catalog, await ddlx.relations(other_relations))
    _remember_entries(catalog, await ddlx.functions(function_oids))
    _remember_entries(catalog, await ddlx.constraints(constraint_oids))
    _remember_entries(catalog, await ddlx.triggers(trigger_oids))
    _remember_entries(catalog, await ddlx.databases(database_oids))
    _remember_entries(catalog, await ddlx.roles(role_oids))
    _remember_entries(catalog, await ddlx.tablespaces(tablespace_oids))
    return catalog
