from __future__ import annotations

import asyncio
import json
from typing import Any

from pg_diag.ddlx import DdlExtractor
from pg_diag.ddlx import assemble, queries


def rel(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "oid": 1001,
        "relkind": "r",
        "relpersistence": "p",
        "identifier": "public.t",
        "reltype": 0,
        "relispartition": False,
        "relispopulated": True,
        "relhasoids": False,
        "partition_bound": None,
        "partition_key": None,
        "of_type": None,
        "reloptions": None,
        "access_method": "heap",
        "tablespace": None,
        "view_definition": None,
        "index_definition": None,
        "parents": None,
        "foreign_server": None,
        "foreign_options_sql": None,
    }
    base.update(overrides)
    return base


def col(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "table_oid": 1001,
        "attnum": 1,
        "name_q": "id",
        "type_name": "integer",
        "not_null": False,
        "is_local": True,
        "identity": "",
        "generated": "",
        "default_expr": None,
        "collation_sql": None,
        "fdw_options_sql": None,
    }
    base.update(overrides)
    return base


def con(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "oid": 3001,
        "table_oid": 1001,
        "domain_oid": 0,
        "name_q": "t_check",
        "contype": "c",
        "is_local": True,
        "definition": "CHECK ((id > 0))",
        "table_identifier": "public.t",
        "domain_identifier": None,
    }
    base.update(overrides)
    return base


def test_create_table_plain() -> None:
    columns = [
        col(name_q="id", not_null=True, default_expr="nextval('public.t_id_seq'::regclass)"),
        col(attnum=2, name_q="title", type_name="text", collation_sql='pg_catalog."C"'),
    ]
    constraints = [
        con(name_q="t_check"),
        con(oid=3002, name_q="t_pkey", contype="p", definition="PRIMARY KEY (id)"),
    ]
    text = assemble.create_table(
        rel(relpersistence="u", reloptions="fillfactor = 90", tablespace="fast"),
        columns,
        constraints,
    )
    assert text == (
        "CREATE UNLOGGED TABLE public.t (\n"
        "    id integer NOT NULL DEFAULT nextval('public.t_id_seq'::regclass),\n"
        '    title text COLLATE pg_catalog."C",\n'
        "    CONSTRAINT t_pkey PRIMARY KEY (id),\n"
        "    CONSTRAINT t_check CHECK ((id > 0))\n"
        ")\n"
        "WITH (fillfactor = 90)\n"
        "TABLESPACE fast;"
    )


def test_create_table_identity_and_generated() -> None:
    columns = [
        col(name_q="id", type_name="bigint", not_null=True, identity="a"),
        col(
            attnum=2,
            name_q="doubled",
            type_name="bigint",
            generated="s",
            default_expr="(id * 2)",
        ),
    ]
    text = assemble.create_table(rel(), columns, [])
    assert "id bigint GENERATED ALWAYS AS IDENTITY" in text
    assert "NOT NULL GENERATED ALWAYS" not in text
    assert "doubled bigint GENERATED ALWAYS AS ((id * 2)) STORED" in text
    assert "DEFAULT (id * 2)" not in text


def test_create_table_partition_child_defers_local_constraints() -> None:
    text = assemble.create_table(
        rel(
            identifier="public.t_p1",
            relispartition=True,
            parents="public.t",
            partition_bound="FOR VALUES FROM (1) TO (10)",
        ),
        [col()],
        [con(table_identifier="public.t_p1")],
    )
    assert text == (
        "CREATE TABLE public.t_p1\n"
        "    PARTITION OF public.t\n"
        "    FOR VALUES FROM (1) TO (10);\n"
        "ALTER TABLE public.t_p1\n"
        "    ADD CONSTRAINT t_check CHECK ((id > 0));"
    )


def test_create_table_partitioned_parent_and_inherits() -> None:
    parent = assemble.create_table(
        rel(relkind="p", partition_key="RANGE (id)"), [col()], []
    )
    assert parent.endswith(")\nPARTITION BY RANGE (id);")

    child = assemble.create_table(
        rel(identifier="public.child", parents="public.base"),
        [col(is_local=False), col(attnum=2, name_q="extra", type_name="text")],
        [],
    )
    assert "extra text" in child
    assert "id integer" not in child
    assert child.endswith(")\nINHERITS (public.base);")


def test_create_table_typed_and_oids() -> None:
    typed = assemble.create_table(rel(of_type="public.person_t"), [col()], [])
    assert typed == "CREATE TABLE public.t\n    OF public.person_t;"

    with_oids = assemble.create_table(
        rel(relhasoids=True, reloptions="fillfactor = 70"), [col()], []
    )
    assert "WITH (fillfactor = 70, oids = true)" in with_oids


def test_create_foreign_table() -> None:
    text = assemble.create_table(
        rel(
            relkind="f",
            identifier="public.ft",
            foreign_server="remote",
            foreign_options_sql="schema_name 'public', table_name 't'",
        ),
        [col(fdw_options_sql="column_name 'id'")],
        [],
    )
    assert text.startswith("CREATE FOREIGN TABLE public.ft (\n")
    assert "id integer OPTIONS (column_name 'id')" in text
    assert text.endswith("SERVER remote OPTIONS (schema_name 'public', table_name 't');")


def test_constraint_filtering_and_order() -> None:
    constraints = [
        con(name_q="z_check"),
        con(oid=1, name_q="a_fkey", contype="f", definition="FOREIGN KEY (id) REFERENCES x(id)"),
        con(oid=2, name_q="a_pkey", contype="p", definition="PRIMARY KEY (id)"),
        con(oid=3, name_q="inherited", is_local=False),
        con(oid=4, name_q="id_not_null", contype="n", definition="NOT NULL id"),
    ]
    kept = assemble.table_constraint_clauses(constraints)
    assert [c["name_q"] for c in kept] == ["a_pkey", "a_fkey", "z_check"]


def test_create_view_and_materialized_view() -> None:
    view = assemble.create_view(
        rel(
            relkind="v",
            identifier="public.v",
            reloptions="security_barrier=true",
            view_definition=" SELECT 1;",
        )
    )
    assert view == (
        "CREATE OR REPLACE VIEW public.v\nWITH (security_barrier=true) AS\nSELECT 1;"
    )

    matview = assemble.create_materialized_view(
        rel(
            relkind="m",
            identifier="public.mv",
            relispopulated=False,
            view_definition=" SELECT 1;",
        )
    )
    assert matview == "CREATE MATERIALIZED VIEW public.mv AS\nSELECT 1\n  WITH NO DATA;"


def test_create_sequence() -> None:
    text = assemble.create_sequence(
        rel(relkind="S", identifier="public.s"),
        {
            "data_type": "smallint",
            "start_value": 5,
            "increment": 2,
            "min_value": 1,
            "max_value": 32767,
            "cache_size": 1,
            "cycle": True,
            "owned_by": "public.t.id",
        },
    )
    assert text == (
        "CREATE SEQUENCE public.s\n"
        "    AS smallint\n"
        "    START WITH 5\n"
        "    INCREMENT BY 2\n"
        "    MINVALUE 1\n"
        "    MAXVALUE 32767\n"
        "    CACHE 1\n"
        "    CYCLE;\n"
        "ALTER SEQUENCE public.s OWNED BY public.t.id;"
    )


def test_create_index_and_trigger() -> None:
    invalid = assemble.create_index(
        {"index_definition": "CREATE INDEX i ON public.t USING btree (id)", "is_valid": False}
    )
    assert invalid == (
        "CREATE INDEX i\n    ON public.t USING btree (id);\n"
        "-- WARNING: this index is marked INVALID"
    )

    wide = assemble.create_index(
        {
            "index_definition": "CREATE INDEX part ON public.orders USING btree (amount) "
            "WITH (fillfactor='80') WHERE (amount > (100)::numeric)",
            "is_valid": True,
        }
    )
    assert wide == (
        "CREATE INDEX part\n"
        "    ON public.orders USING btree (amount)\n"
        "    WITH (fillfactor='80')\n"
        "    WHERE (amount > (100)::numeric);"
    )

    disabled = assemble.create_trigger(
        {
            "definition": "CREATE TRIGGER trg BEFORE INSERT ON public.t "
            "FOR EACH ROW EXECUTE FUNCTION f()",
            "enabled": "D",
            "table_identifier": "public.t",
            "name_q": "trg",
        }
    )
    assert disabled == (
        "CREATE TRIGGER trg\n"
        "    BEFORE INSERT ON public.t\n"
        "    FOR EACH ROW\n"
        "    EXECUTE FUNCTION f();\n"
        "ALTER TABLE public.t DISABLE TRIGGER trg;"
    )


def test_break_clauses_respects_quotes_and_parens() -> None:
    literal = "CHECK ((note <> 'keep ON UPDATE here'::text))"
    assert assemble.break_clauses(literal, ("ON UPDATE",), "  ") == literal

    fk = (
        "FOREIGN KEY (staff_id) REFERENCES pagila.staff(staff_id) "
        "MATCH FULL ON UPDATE CASCADE ON DELETE RESTRICT NOT VALID"
    )
    formatted = assemble.break_clauses(fk, assemble._CONSTRAINT_BREAKS, "    ")
    assert formatted == (
        "FOREIGN KEY (staff_id)\n"
        "    REFERENCES pagila.staff(staff_id)\n"
        "    MATCH FULL\n"
        "    ON UPDATE CASCADE\n"
        "    ON DELETE RESTRICT\n"
        "    NOT VALID"
    )
    quoted_ident = 'CREATE INDEX x ON public."my ON table" USING btree (id)'
    assert assemble.break_clauses(quoted_ident, ("ON",), "    ") == (
        'CREATE INDEX x\n    ON public."my ON table" USING btree (id)'
    )


def test_add_constraint_targets() -> None:
    on_table = assemble.add_constraint(con())
    assert on_table == "ALTER TABLE public.t\n    ADD CONSTRAINT t_check CHECK ((id > 0));"

    fk = assemble.add_constraint(
        con(
            name_q="t_fkey",
            contype="f",
            definition="FOREIGN KEY (x) REFERENCES public.p(x) ON DELETE CASCADE",
        )
    )
    assert fk == (
        "ALTER TABLE public.t\n"
        "    ADD CONSTRAINT t_fkey FOREIGN KEY (x)\n"
        "    REFERENCES public.p(x)\n"
        "    ON DELETE CASCADE;"
    )

    on_domain = assemble.add_constraint(
        con(table_identifier=None, domain_identifier="public.d", name_q="d_check")
    )
    assert on_domain == (
        "ALTER DOMAIN public.d\n    ADD CONSTRAINT d_check CHECK ((id > 0));"
    )


def test_create_types() -> None:
    enum = assemble.create_enum_type(
        {"identifier": "public.mood", "enum_labels": "'sad', 'ok', 'happy'"}
    )
    assert enum == "CREATE TYPE public.mood AS ENUM (\n    'sad', 'ok', 'happy'\n);"

    domain = assemble.create_domain(
        {
            "identifier": "public.positive",
            "domain_base": "integer",
            "domain_default": "1",
            "domain_not_null": True,
            "domain_collation_sql": None,
        },
        [
            con(name_q="positive_check", definition="CHECK (VALUE > 0)"),
            con(oid=9, name_q="positive_not_null", contype="n", definition="NOT NULL"),
        ],
    )
    assert domain == (
        "CREATE DOMAIN public.positive AS integer\n    DEFAULT 1\n    NOT NULL\n"
        "    CONSTRAINT positive_check CHECK (VALUE > 0);"
    )

    composite = assemble.create_composite_type(
        {"identifier": "public.pair"},
        [col(name_q="a"), col(attnum=2, name_q="b", type_name="text")],
    )
    assert composite == "CREATE TYPE public.pair AS (\n    a integer,\n    b text\n);"

    range_type = assemble.create_range_type(
        {
            "identifier": "public.floatrange",
            "range_subtype": "double precision",
            "range_subtype_opclass": None,
            "range_collation_sql": None,
            "range_canonical": None,
            "range_subtype_diff": "float8mi",
        }
    )
    assert range_type == (
        "CREATE TYPE public.floatrange AS RANGE (\n"
        "    SUBTYPE = double precision,\n"
        "    SUBTYPE_DIFF = float8mi\n);"
    )


def test_create_database() -> None:
    text = assemble.create_database(
        {
            "name_q": "app",
            "encoding": "UTF8",
            "lc_collate": "C.UTF-8",
            "lc_ctype": "C.UTF-8",
            "locale_provider": "icu",
            "provider_locale": "en-US",
            "icu_rules": None,
            "tablespace": None,
            "connection_limit": 20,
            "allow_connections": True,
            "is_template": False,
            "settings_sql": "ALTER DATABASE app SET work_mem TO '64MB';",
        }
    )
    assert text == (
        "CREATE DATABASE app\n"
        "    WITH ENCODING 'UTF8'\n"
        "    LC_COLLATE 'C.UTF-8'\n"
        "    LC_CTYPE 'C.UTF-8'\n"
        "    LOCALE_PROVIDER icu\n"
        "    ICU_LOCALE 'en-US'\n"
        "    CONNECTION LIMIT 20;\n"
        "ALTER DATABASE app SET work_mem TO '64MB';"
    )


def test_databases_sql_version_forks() -> None:
    assert "datlocale" in queries.databases_sql(170000)
    assert "daticulocale" in queries.databases_sql(160000)
    assert "daticurules" not in queries.databases_sql(150000)
    assert "datlocprovider" not in queries.databases_sql(140000)


def test_extractor_databases() -> None:
    conn = FakeConn(
        [
            {
                "oid": 5,
                "identifier": "postgres",
                "name_q": "postgres",
                "encoding": "UTF8",
                "lc_collate": "C",
                "lc_ctype": "C",
                "locale_provider": None,
                "provider_locale": None,
                "icu_rules": None,
                "connection_limit": -1,
                "allow_connections": True,
                "is_template": False,
                "tablespace": None,
                "settings_sql": None,
            }
        ]
    )
    result = asyncio.run(DdlExtractor(conn, 150000).databases([5]))
    assert result[5].kind == "database"
    assert result[5].ddl == "CREATE DATABASE postgres\n    WITH ENCODING 'UTF8'\n    LC_COLLATE 'C'\n    LC_CTYPE 'C';"


def test_create_role() -> None:
    text = assemble.create_role(
        {
            "name_q": "lab_admin",
            "is_superuser": False,
            "inherit": True,
            "create_role": False,
            "create_db": True,
            "can_login": False,
            "replication": False,
            "bypass_rls": False,
            "connection_limit": -1,
            "valid_until": None,
            "memberships_sql": "GRANT lab_readwrite TO lab_admin WITH ADMIN OPTION;",
            "settings_sql": None,
        }
    )
    assert text == (
        "CREATE ROLE lab_admin\n    CREATEDB\n    NOLOGIN;\n"
        "GRANT lab_readwrite TO lab_admin WITH ADMIN OPTION;"
    )
    login = assemble.create_role(
        {
            "name_q": "lab_app",
            "can_login": True,
            "inherit": True,
            "connection_limit": 20,
            "valid_until": "2027-06-30 00:00:00+00",
        }
    )
    assert login == (
        "CREATE ROLE lab_app\n    LOGIN\n    CONNECTION LIMIT 20\n"
        "    VALID UNTIL '2027-06-30 00:00:00+00';"
    )


def test_roles_sql_has_no_password_material() -> None:
    sql = queries.roles_sql(150000)
    assert "pg_roles" in sql
    assert "pg_authid" not in sql
    # the only password mention is the sensitive-setting redaction filter
    assert "rolpassword" not in sql.lower()
    assert "quote_literal('[REDACTED]')" in sql


def test_roles_sql_membership_flags_fork() -> None:
    legacy = queries.roles_sql(150000)
    assert "WITH ADMIN OPTION" in legacy
    assert "inherit_option" not in legacy
    modern = queries.roles_sql(160000)
    assert "m.inherit_option" in modern and "m.set_option" in modern
    assert "', INHERIT '" in modern and "', SET '" in modern


def test_settings_redaction_in_role_and_database_sql() -> None:
    for sql in (queries.roles_sql(150000), queries.databases_sql(150000)):
        assert queries.SENSITIVE_SETTING_REGEX in sql
        assert "quote_literal('[REDACTED]')" in sql


def test_extractor_roles_and_tablespaces() -> None:
    conn = FakeConn(
        [
            {
                "oid": 8001,
                "identifier": "lab_app",
                "name_q": "lab_app",
                "is_superuser": False,
                "inherit": True,
                "create_role": False,
                "create_db": False,
                "can_login": True,
                "replication": False,
                "bypass_rls": False,
                "connection_limit": -1,
                "valid_until": None,
                "memberships_sql": None,
                "settings_sql": None,
            }
        ]
    )
    result = asyncio.run(DdlExtractor(conn, 150000).roles([8001]))
    assert result[8001].kind == "role"
    assert result[8001].ddl == "CREATE ROLE lab_app\n    LOGIN;"

    conn = FakeConn(
        [
            {"oid": 1663, "identifier": "pg_default", "name_q": "pg_default",
             "location": "", "options": None},
            {"oid": 90001, "identifier": "fast", "name_q": "fast",
             "location": "/ssd/ts", "options": "random_page_cost=1.1"},
        ]
    )
    result = asyncio.run(DdlExtractor(conn, 150000).tablespaces([1663, 90001]))
    assert result[1663].ddl is not None
    assert result[1663].ddl.startswith("-- pg_default is a built-in tablespace")
    assert result[90001].ddl == (
        "CREATE TABLESPACE fast\n    LOCATION '/ssd/ts'\n    WITH (random_page_cost=1.1);"
    )


def test_query_version_forks() -> None:
    assert "''::text as generated" in queries.columns_sql(110000)
    assert "a.attgenerated::text as generated" in queries.columns_sql(120000)
    assert "c.relhasoids" in queries.relations_sql(110000)
    assert "false as relhasoids" in queries.relations_sql(120000)
    assert "p.proisagg" in queries.functions_sql(100000)
    assert "p.prokind" in queries.functions_sql(110000)


def test_query_filter_variants() -> None:
    assert "c.relkind in ('r', 'p', 'f')" in queries.relations_sql(150000, tables_only=True)
    assert "and c.relkind in ('r', 'p', 'f')" not in queries.relations_sql(150000)
    assert "tt.typrelid" in queries.columns_sql(150000, of_types=True)
    assert "tg.tgfoid" in queries.functions_sql(150000, of_table_triggers=True)
    assert "c2.reltype" in queries.types_sql(of_composite_relations=True)


def test_sectioned_sql_shape() -> None:
    sql = queries.sectioned_sql([("a", "select 1 as x"), ("b", "select 2 as y")])
    assert sql.count("union all") == 1
    assert "'a'::text as section" in sql
    assert "'b'::text as section" in sql
    assert "to_jsonb(q)::text as payload" in sql


class FakeConn:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        self.calls.append((sql, args))
        return self.rows


def sec(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"section": name, "payload": json.dumps(payload)}


def test_extractor_relations_dispatch_in_one_round_trip() -> None:
    conn = FakeConn(
        [
            sec("relation", rel(oid=1001)),
            sec(
                "relation",
                rel(oid=1002, relkind="v", identifier="public.v", view_definition=" SELECT 1;"),
            ),
            sec("relation", rel(oid=1003, relkind="S", identifier="public.s")),
            sec("relation", rel(oid=1004, relkind="t", identifier="pg_toast.pg_toast_1001")),
            sec("column", col(table_oid=1001)),
            sec("constraint", con(table_oid=1001)),
            sec(
                "sequence",
                {
                    "oid": 1003,
                    "data_type": "bigint",
                    "start_value": 1,
                    "increment": 1,
                    "min_value": 1,
                    "max_value": 9223372036854775807,
                    "cache_size": 1,
                    "cycle": False,
                    "owned_by": None,
                },
            ),
        ]
    )
    result = asyncio.run(DdlExtractor(conn, 150000).relations([1001, 1002, 1003, 1004]))

    assert len(conn.calls) == 1
    assert conn.calls[0][1] == ([1001, 1002, 1003, 1004],)
    assert result[1001].kind == "table"
    assert result[1001].ddl is not None and result[1001].ddl.startswith("CREATE TABLE public.t (")
    assert "CONSTRAINT t_check" in result[1001].ddl
    assert result[1002].ddl == "CREATE OR REPLACE VIEW public.v AS\nSELECT 1;"
    assert result[1003].ddl is not None and result[1003].ddl.startswith("CREATE SEQUENCE public.s")
    assert result[1004].ddl is None
    assert result[1004].reason is not None and "TOAST" in result[1004].reason


def test_extractor_composite_relation_delegates_to_type() -> None:
    conn = FakeConn(
        [
            sec("relation", rel(oid=1005, relkind="c", identifier="public.pair", reltype=2005)),
            sec("type", {"oid": 2005, "typtype": "c", "identifier": "public.pair"}),
            sec("column", col(table_oid=1005, name_q="a")),
        ]
    )
    result = asyncio.run(DdlExtractor(conn, 150000).relations([1005]))
    assert len(conn.calls) == 1
    assert result[1005].kind == "composite type"
    assert result[1005].ddl == "CREATE TYPE public.pair AS (\n    a integer\n);"


def test_extractor_tables_bundle_in_one_round_trip() -> None:
    conn = FakeConn(
        [
            sec("relation", rel(oid=1001)),
            sec("column", col(table_oid=1001)),
            sec("constraint", con(table_oid=1001)),
            sec(
                "index",
                {
                    "oid": 6001,
                    "table_oid": 1001,
                    "identifier": "public.t_idx",
                    "index_definition": "CREATE INDEX t_idx ON public.t USING btree (id)",
                    "is_valid": True,
                    "backs_constraint": False,
                },
            ),
            sec(
                "trigger",
                {
                    "oid": 5001,
                    "table_oid": 1001,
                    "function_oid": 4001,
                    "name_q": "trg",
                    "table_identifier": "public.t",
                    "definition": "CREATE TRIGGER trg ...",
                    "enabled": "O",
                },
            ),
            sec(
                "function",
                {
                    "oid": 4001,
                    "identifier": "public.touch()",
                    "prokind": "f",
                    "definition": "CREATE OR REPLACE FUNCTION public.touch() ...",
                },
            ),
        ]
    )
    result = asyncio.run(DdlExtractor(conn, 150000).tables_bundle([1001]))
    assert len(conn.calls) == 1
    bundle = result[1001]
    assert bundle.table.ddl is not None and "CONSTRAINT t_check" in bundle.table.ddl
    assert [i.identifier for i in bundle.indexes] == ["public.t_idx"]
    assert [t.identifier for t in bundle.triggers] == ["trg ON public.t"]
    assert [f.identifier for f in bundle.trigger_functions] == ["public.touch()"]


def test_extractor_functions_and_aggregates() -> None:
    conn = FakeConn(
        [
            {
                "oid": 4001,
                "identifier": "public.f()",
                "prokind": "f",
                "definition": "CREATE OR REPLACE FUNCTION public.f() ...",
            },
            {
                "oid": 4002,
                "identifier": "public.agg(integer)",
                "prokind": "a",
                "definition": None,
            },
        ]
    )
    result = asyncio.run(DdlExtractor(conn, 150000).functions([4001, 4002]))
    assert result[4001].ddl == "CREATE OR REPLACE FUNCTION public.f() ...;"
    assert result[4002].ddl is None
    assert result[4002].kind == "aggregate"


def test_extractor_triggers_for_tables_grouping() -> None:
    trigger = {
        "oid": 5001,
        "table_oid": 1001,
        "function_oid": 4001,
        "name_q": "trg",
        "table_identifier": "public.t",
        "definition": "CREATE TRIGGER trg ...",
        "enabled": "O",
    }
    conn = FakeConn([trigger])
    result = asyncio.run(DdlExtractor(conn, 150000).triggers_for_tables([1001]))
    assert list(result) == [1001]
    assert result[1001][0].identifier == "trg ON public.t"
    assert result[1001][0].ddl == "CREATE TRIGGER trg ...;"


def test_extractor_empty_input_issues_no_queries() -> None:
    conn = FakeConn([])
    extractor = DdlExtractor(conn, 150000)
    assert asyncio.run(extractor.relations([])) == {}
    assert asyncio.run(extractor.functions([])) == {}
    assert asyncio.run(extractor.types([])) == {}
    assert asyncio.run(extractor.tables_bundle([])) == {}
    assert conn.calls == []
