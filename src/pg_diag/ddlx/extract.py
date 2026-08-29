"""Batched, read-only DDL extraction over an asyncpg-style connection.

The extractor never creates anything in the observed database, and every
public method costs exactly ONE round trip: the per-catalog queries are
combined into a single sectioned UNION ALL statement (see
queries.sectioned_sql), so the method works unchanged over high-latency
links between a DBA workstation and the observed server.  Callers are
expected to run it inside a read-only transaction and to bound the oid
batches themselves.

Typical use from a report python source::

    version = int(await ctx.conn.fetchval("show server_version_num"))
    ddlx = DdlExtractor(ctx.conn, version)
    async with ctx.conn.transaction(readonly=True):
        bundles = await ddlx.tables_bundle(table_oids)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence

from pg_diag.ddlx import assemble, queries

Record = dict[str, Any]

_RELKIND_NAMES = {
    "r": "table",
    "p": "partitioned table",
    "f": "foreign table",
    "v": "view",
    "m": "materialized view",
    "S": "sequence",
    "i": "index",
    "I": "partitioned index",
    "c": "composite type",
    "t": "TOAST table",
}

_TYPTYPE_NAMES = {
    "e": "enum type",
    "d": "domain",
    "r": "range type",
    "c": "composite type",
    "b": "base type",
    "p": "pseudo-type",
    "m": "multirange type",
}

_PROKIND_NAMES = {
    "f": "function",
    "p": "procedure",
    "w": "window function",
    "a": "aggregate",
}


@dataclass(frozen=True)
class ObjectDdl:
    oid: int
    kind: str
    identifier: str
    ddl: str | None
    reason: str | None = None


@dataclass(frozen=True)
class TableBundle:
    """One table with everything a schema browser shows next to it."""

    table: ObjectDdl
    indexes: tuple[ObjectDdl, ...]
    triggers: tuple[ObjectDdl, ...]
    trigger_functions: tuple[ObjectDdl, ...]


def _unsupported(oid: int, kind: str, identifier: str, reason: str) -> ObjectDdl:
    return ObjectDdl(oid=oid, kind=kind, identifier=identifier, ddl=None, reason=reason)


def _grouped(records: list[Record], key: str, order: str | None = None) -> dict[int, list[Record]]:
    grouped: dict[int, list[Record]] = {}
    for record in records:
        grouped.setdefault(record[key], []).append(record)
    if order is not None:
        for group in grouped.values():
            group.sort(key=lambda r: r[order])
    return grouped


class DdlExtractor:
    def __init__(self, conn: Any, server_version_num: int) -> None:
        self._conn = conn
        self._version = int(server_version_num)

    async def _fetch(self, sql: str, oids: Sequence[int]) -> list[Record]:
        if not oids:
            return []
        rows = await self._conn.fetch(sql, [int(oid) for oid in oids])
        return [dict(row) for row in rows]

    async def _fetch_sections(
        self, sections: Sequence[tuple[str, str]], oids: Sequence[int]
    ) -> dict[str, list[Record]]:
        """Run all sections as one statement; one round trip for the whole batch."""
        grouped: dict[str, list[Record]] = {}
        for row in await self._fetch(queries.sectioned_sql(sections), oids):
            grouped.setdefault(row["section"], []).append(json.loads(row["payload"]))
        return grouped

    async def relations(self, oids: Sequence[int]) -> dict[int, ObjectDdl]:
        """DDL for pg_class oids: tables, views, sequences, indexes, composites."""
        data = await self._fetch_sections(
            [
                ("relation", queries.relations_sql(self._version)),
                ("column", queries.columns_sql(self._version)),
                ("constraint", queries.constraints_for_tables_sql()),
                ("sequence", queries.sequences_sql()),
                ("type", queries.types_sql(of_composite_relations=True)),
            ],
            oids,
        )
        columns = _grouped(data.get("column", []), "table_oid", order="attnum")
        constraints = _grouped(data.get("constraint", []), "table_oid", order="oid")
        sequences = {r["oid"]: r for r in data.get("sequence", [])}
        composite_types = {r["oid"]: r for r in data.get("type", [])}

        out: dict[int, ObjectDdl] = {}
        for rel in data.get("relation", []):
            oid = rel["oid"]
            kind = _RELKIND_NAMES.get(rel["relkind"], f"relkind {rel['relkind']}")
            identifier = rel["identifier"]
            if rel["relkind"] in ("r", "p", "f"):
                ddl = assemble.create_table(
                    rel, columns.get(oid, []), constraints.get(oid, [])
                )
            elif rel["relkind"] == "v":
                ddl = assemble.create_view(rel)
            elif rel["relkind"] == "m":
                ddl = assemble.create_materialized_view(rel)
            elif rel["relkind"] == "S":
                sequence = sequences.get(oid)
                if sequence is None:
                    out[oid] = _unsupported(oid, kind, identifier, "pg_sequence row not found")
                    continue
                ddl = assemble.create_sequence(rel, sequence)
            elif rel["relkind"] in ("i", "I"):
                ddl = assemble.create_index(
                    {"index_definition": rel["index_definition"], "is_valid": True}
                )
            elif rel["relkind"] == "c":
                composite = composite_types.get(rel["reltype"])
                if composite is None:
                    out[oid] = _unsupported(oid, kind, identifier, "composite type not found")
                    continue
                ddl = assemble.create_composite_type(composite, columns.get(oid, []))
                out[oid] = ObjectDdl(
                    oid=oid, kind=kind, identifier=composite["identifier"], ddl=ddl
                )
                continue
            else:
                out[oid] = _unsupported(
                    oid, kind, identifier, f"DDL extraction is not supported for a {kind}"
                )
                continue
            out[oid] = ObjectDdl(oid=oid, kind=kind, identifier=identifier, ddl=ddl)
        return out

    async def tables_bundle(self, oids: Sequence[int]) -> dict[int, TableBundle]:
        """Tables with their indexes, triggers, and trigger functions.

        One round trip for the whole batch; non-table oids are absent from
        the result.
        """
        data = await self._fetch_sections(
            [
                ("relation", queries.relations_sql(self._version, tables_only=True)),
                ("column", queries.columns_sql(self._version)),
                ("constraint", queries.constraints_for_tables_sql()),
                ("index", queries.indexes_for_tables_sql()),
                ("trigger", queries.triggers_for_tables_sql()),
                ("function", queries.functions_sql(self._version, of_table_triggers=True)),
            ],
            oids,
        )
        columns = _grouped(data.get("column", []), "table_oid", order="attnum")
        constraints = _grouped(data.get("constraint", []), "table_oid", order="oid")
        indexes = _grouped(data.get("index", []), "table_oid", order="oid")
        triggers = _grouped(data.get("trigger", []), "table_oid", order="name_q")
        functions = {
            r["oid"]: self._function_ddl(r) for r in data.get("function", [])
        }

        out: dict[int, TableBundle] = {}
        for rel in data.get("relation", []):
            oid = rel["oid"]
            kind = _RELKIND_NAMES.get(rel["relkind"], f"relkind {rel['relkind']}")
            table = ObjectDdl(
                oid=oid,
                kind=kind,
                identifier=rel["identifier"],
                ddl=assemble.create_table(rel, columns.get(oid, []), constraints.get(oid, [])),
            )
            table_triggers = [self._trigger_ddl(r) for r in triggers.get(oid, [])]
            function_oids = {
                r["function_oid"]
                for r in triggers.get(oid, [])
                if r.get("function_oid") in functions
            }
            out[oid] = TableBundle(
                table=table,
                indexes=tuple(
                    ObjectDdl(
                        oid=r["oid"],
                        kind="index",
                        identifier=r["identifier"],
                        ddl=assemble.create_index(r),
                    )
                    for r in indexes.get(oid, [])
                    # Constraint-backed indexes are already created by the
                    # PRIMARY KEY/UNIQUE/EXCLUDE clauses inside CREATE TABLE.
                    if not r.get("backs_constraint")
                ),
                triggers=tuple(table_triggers),
                trigger_functions=tuple(
                    functions[f_oid] for f_oid in sorted(function_oids)
                ),
            )
        return out

    async def functions(self, oids: Sequence[int]) -> dict[int, ObjectDdl]:
        """DDL for pg_proc oids; aggregates are reported as unsupported."""
        records = await self._fetch(queries.functions_sql(self._version), oids)
        return {r["oid"]: self._function_ddl(r) for r in records}

    def _function_ddl(self, record: Record) -> ObjectDdl:
        kind = _PROKIND_NAMES.get(record["prokind"], f"prokind {record['prokind']}")
        if record["definition"] is None:
            return _unsupported(
                record["oid"],
                kind,
                record["identifier"],
                "aggregate definitions are not supported by pg_get_functiondef",
            )
        return ObjectDdl(
            oid=record["oid"],
            kind=kind,
            identifier=record["identifier"],
            ddl=assemble.create_function(record),
        )

    async def triggers(self, oids: Sequence[int]) -> dict[int, ObjectDdl]:
        """DDL for pg_trigger oids (internal triggers are never returned)."""
        out: dict[int, ObjectDdl] = {}
        for record in await self._fetch(queries.triggers_by_oid_sql(), oids):
            out[record["oid"]] = self._trigger_ddl(record)
        return out

    async def triggers_for_tables(
        self, table_oids: Sequence[int]
    ) -> dict[int, list[ObjectDdl]]:
        """Non-internal triggers grouped by their table oid."""
        records = await self._fetch(queries.triggers_for_tables_sql(), table_oids)
        return {
            table_oid: [self._trigger_ddl(record) for record in group]
            for table_oid, group in _grouped(records, "table_oid", order="name_q").items()
        }

    def _trigger_ddl(self, record: Record) -> ObjectDdl:
        name = record["name_q"] + " ON " + record["table_identifier"]
        return ObjectDdl(
            oid=record["oid"],
            kind="trigger",
            identifier=name,
            ddl=assemble.create_trigger(record),
        )

    async def constraints(self, oids: Sequence[int]) -> dict[int, ObjectDdl]:
        """DDL (as ALTER TABLE/DOMAIN ... ADD CONSTRAINT) for pg_constraint oids."""
        out: dict[int, ObjectDdl] = {}
        for record in await self._fetch(queries.constraints_by_oid_sql(), oids):
            target = record.get("table_identifier") or record.get("domain_identifier") or ""
            out[record["oid"]] = ObjectDdl(
                oid=record["oid"],
                kind="constraint",
                identifier=record["name_q"] + " ON " + target,
                ddl=assemble.add_constraint(record),
            )
        return out

    async def indexes_for_tables(
        self, table_oids: Sequence[int]
    ) -> dict[int, list[ObjectDdl]]:
        """Index DDL grouped by table oid, including invalid-index warnings."""
        records = await self._fetch(queries.indexes_for_tables_sql(), table_oids)
        return {
            table_oid: [
                ObjectDdl(
                    oid=record["oid"],
                    kind="index",
                    identifier=record["identifier"],
                    ddl=assemble.create_index(record),
                )
                for record in group
            ]
            for table_oid, group in _grouped(records, "table_oid", order="oid").items()
        }

    async def roles(self, oids: Sequence[int]) -> dict[int, ObjectDdl]:
        """DDL for pg_authid oids: CREATE ROLE (never passwords) + grants + settings."""
        out: dict[int, ObjectDdl] = {}
        for record in await self._fetch(queries.roles_sql(self._version), oids):
            out[record["oid"]] = ObjectDdl(
                oid=record["oid"],
                kind="role",
                identifier=record["identifier"],
                ddl=assemble.create_role(record),
            )
        return out

    async def tablespaces(self, oids: Sequence[int]) -> dict[int, ObjectDdl]:
        """DDL for pg_tablespace oids; built-ins get an explanatory comment."""
        out: dict[int, ObjectDdl] = {}
        for record in await self._fetch(queries.tablespaces_sql(), oids):
            out[record["oid"]] = ObjectDdl(
                oid=record["oid"],
                kind="tablespace",
                identifier=record["identifier"],
                ddl=assemble.create_tablespace(record),
            )
        return out

    async def databases(self, oids: Sequence[int]) -> dict[int, ObjectDdl]:
        """DDL for pg_database oids: CREATE DATABASE plus ALTER ... SET lines."""
        out: dict[int, ObjectDdl] = {}
        for record in await self._fetch(queries.databases_sql(self._version), oids):
            out[record["oid"]] = ObjectDdl(
                oid=record["oid"],
                kind="database",
                identifier=record["identifier"],
                ddl=assemble.create_database(record),
            )
        return out

    async def types(self, oids: Sequence[int]) -> dict[int, ObjectDdl]:
        """DDL for pg_type oids: enums, domains, ranges, and composite types."""
        data = await self._fetch_sections(
            [
                ("type", queries.types_sql()),
                ("constraint", queries.constraints_for_domains_sql()),
                ("column", queries.columns_sql(self._version, of_types=True)),
            ],
            oids,
        )
        domain_constraints = _grouped(data.get("constraint", []), "domain_oid", order="oid")
        composite_columns = _grouped(data.get("column", []), "table_oid", order="attnum")

        out: dict[int, ObjectDdl] = {}
        for record in data.get("type", []):
            oid = record["oid"]
            kind = _TYPTYPE_NAMES.get(record["typtype"], f"typtype {record['typtype']}")
            identifier = record["identifier"]
            if record["typtype"] == "e":
                ddl = assemble.create_enum_type(record)
            elif record["typtype"] == "d":
                ddl = assemble.create_domain(record, domain_constraints.get(oid, []))
            elif record["typtype"] == "r":
                ddl = assemble.create_range_type(record)
            elif record["typtype"] == "c":
                ddl = assemble.create_composite_type(
                    record, composite_columns.get(record["typrelid"], [])
                )
            else:
                out[oid] = _unsupported(
                    oid, kind, identifier, f"DDL extraction is not supported for a {kind}"
                )
                continue
            out[oid] = ObjectDdl(oid=oid, kind=kind, identifier=identifier, ddl=ddl)
        return out
