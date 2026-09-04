"""Unit tests for the pure logscan layers: recall, sanitize, csvparse, rle."""

from __future__ import annotations

import json

import pytest

from pg_diag.logscan import auto_explain, csvparse, recall, rle, sanitize
from pg_diag.logscan.item_recall import clauses_for_items
from pg_diag.logscan.model import RawSeries


# --- recall DSL ---


def test_recall_matches_any_all() -> None:
    clauses = recall.compile_clauses([[",ERROR,"], ["still waiting for", "Lock"]])
    assert recall.matches(b"2026-08-31 x,,,,,,,,,,,ERROR,42601,boom", clauses)
    assert recall.matches(b"process still waiting for ShareLock on relation", clauses)
    assert not recall.matches(b"process still waiting for a bus", clauses)


def test_recall_rejects_short_and_non_ascii_fragments() -> None:
    with pytest.raises(recall.RecallError):
        recall.compile_clauses([["abc"]])
    with pytest.raises(recall.RecallError):
        recall.compile_clauses([["ошибка"]])
    with pytest.raises(recall.RecallError):
        recall.compile_clauses([])


def test_recall_awk_condition_escapes() -> None:
    clauses = recall.compile_clauses([['say "hi"', "a\\b12"]])
    condition = recall.to_awk_condition(clauses)
    assert condition == '(index($0, "say \\"hi\\"") > 0 && index($0, "a\\\\b12") > 0)'


def test_lock_wait_recall_rejects_unrelated_multiline_continuations() -> None:
    clauses = clauses_for_items(("server_log.lock_waits",))
    record = (
        b"2026-08-31 10:00:00 UTC,u,d,1,c,s,1,SELECT,start,3/4,1,"
        b"LOG,00000,process 1 acquired ShareLock on transaction 42 after 1500.0 ms"
    )
    continuation = b"the client acquired a connection after retrying the pool"

    assert recall.matches(record, clauses)
    assert not recall.matches(continuation, clauses)


# --- sanitizer ---


def test_sanitize_password_clause() -> None:
    text = sanitize.sanitize_text("ALTER ROLE bob PASSWORD 'sup''er'")
    assert "sup" not in text
    assert "[REDACTED]" in text


def test_sanitize_keeps_auth_failure_prose() -> None:
    text = sanitize.sanitize_text('password authentication failed for user "svc"')
    assert text == 'password authentication failed for user "svc"'


def test_sanitize_uri_credentials_and_tokens() -> None:
    text = sanitize.sanitize_text(
        "connection to postgresql://app:hunter2@db:5432/x failed, token=abc123DEF"
    )
    assert "hunter2" not in text
    assert "abc123DEF" not in text


def test_sanitize_quoted_literals() -> None:
    text = sanitize.sanitize_text("duplicate key value ('bob@example.com') violates x")
    assert "bob@example.com" not in text
    assert "'[LITERAL]'" in text


# --- csv parsing ---


def _record26(message: str = "boom", quoted_user: bool = False) -> bytes:
    user = '"we,ird"' if quoted_user else "alice"
    fields = [
        "2026-08-31 10:00:00.123 UTC",
        user,
        "appdb",
        "4152",
        "127.0.0.1:5000",
        "sess",
        "7",
        "SELECT",
        "2026-08-31 09:00:00 UTC",
        "3/44",
        "778",
        "ERROR",
        "42601",
        message,
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "loc",
        "app",
        "client backend",
        "",
        "12345",
    ]
    return ",".join(fields).encode()


def test_parse_record_pg14_full() -> None:
    parsed = csvparse.parse_record(_record26(), server_version_num=160000)
    assert parsed is not None
    assert parsed.severity == "ERROR"
    assert parsed.sql_state == "42601"
    assert parsed.query_id == 12345
    assert parsed.backend_type == "client backend"
    assert parsed.connection_from == "127.0.0.1:5000"
    assert not parsed.partial


def test_parse_record_extracts_detail() -> None:
    raw = _record26()
    fields = raw.decode().split(",")
    fields[14] = '"Process holding the lock: 4152. Wait queue: 4155."'
    parsed = csvparse.parse_record(",".join(fields).encode(), server_version_num=160000)
    assert parsed is not None
    assert parsed.detail == "Process holding the lock: 4152. Wait queue: 4155."


def test_parse_record_quoted_comma_field() -> None:
    parsed = csvparse.parse_record(_record26(quoted_user=True), server_version_num=160000)
    assert parsed is not None
    assert parsed.user_name == "we,ird"


def test_parse_record_truncated_is_partial() -> None:
    raw = _record26("x" * 50)[:90]  # cut inside the record
    parsed = csvparse.parse_record(raw, server_version_num=160000)
    if parsed is not None:
        assert parsed.partial


def test_parse_record_pg12_no_backend_type() -> None:
    raw = _record26()
    # strip the three v13/v14 columns
    raw = raw.rsplit(b",", 3)[0]
    parsed = csvparse.parse_record(raw, server_version_num=120000)
    assert parsed is not None
    assert parsed.backend_type is None
    assert parsed.query_id is None
    assert not parsed.partial


@pytest.mark.parametrize(
    ("body", "plan_format", "root", "nodes", "query_sample"),
    [
        (
            '{"Query Text":"select 1","Plan":{"Node Type":"Aggregate",'
            '"Plans":[{"Node Type":"Result"}]}}',
            "json",
            "Aggregate",
            2,
            "select 1",
        ),
        (
            '<explain xmlns="http://www.postgresql.org/2009/explain">'
            "<Query-Text>select 2</Query-Text><Plan>"
            "<Node-Type>Index Scan</Node-Type><Plans><Plan><Node-Type>Result</Node-Type>"
            "</Plan></Plans></Plan></explain>",
            "xml",
            "Index Scan",
            2,
            "select 2",
        ),
        (
            'Query Text: "select 1"\nPlan: \n  Node Type: "Hash Join"\n  Plans:\n'
            '    - Node Type: "Seq Scan"',
            "yaml",
            "Hash Join",
            2,
            "select 1",
        ),
        (
            "Query Text: select 1\nAggregate  (cost=1.00..2.00 rows=1 width=8)\n"
            "  ->  Seq Scan on t  (cost=0.00..1.00 rows=1 width=4)",
            "text",
            "Aggregate",
            2,
            "select 1",
        ),
    ],
)
def test_parse_auto_explain_formats(body, plan_format, root, nodes, query_sample) -> None:
    message = f"duration: 123.456 ms  plan:\n{body}"
    parsed = auto_explain.parse_auto_explain(message, complete=True)
    assert parsed is not None
    assert parsed.duration_ms == 123.456
    assert parsed.plan_format == plan_format
    assert parsed.root_node_type == root
    assert parsed.node_count == nodes
    assert parsed.query_sample == query_sample
    if plan_format in {"json", "xml"}:
        assert parsed.viewer_plan is not None
        prefix, viewer_json = parsed.viewer_plan.split("\n", 1)
        assert prefix == "duration: 123.456 ms  plan:"
        viewer_payload = json.loads(viewer_json)
        if plan_format == "xml":
            viewer_payload = viewer_payload[0]
            assert viewer_payload["Query Text"] == "select 2"
            assert viewer_payload["Plan"]["Node Type"] == "Index Scan"
            assert viewer_payload["Plan"]["Plans"][0]["Node Type"] == "Result"
        else:
            assert viewer_payload["Query Text"] == "select 1"
            assert viewer_payload["Plan"]["Node Type"] == "Aggregate"
    else:
        assert parsed.viewer_plan == message
    assert parsed.parsed
    assert parsed.complete


def test_parse_auto_explain_rejects_ordinary_duration_and_marks_bad_plan() -> None:
    assert (
        auto_explain.parse_auto_explain("duration: 5 ms statement: select 1", complete=True) is None
    )
    parsed = auto_explain.parse_auto_explain("duration: 5 ms  plan:\n{bad", complete=False)
    assert parsed is not None
    assert parsed.plan_format == "json"
    assert parsed.query_sample is None
    assert parsed.viewer_plan is None
    assert not parsed.parsed
    assert not parsed.complete


def test_parse_auto_explain_sanitizes_and_caps_query_sample() -> None:
    query = "select * from accounts where password = 'secret' /* " + ("x" * 500) + " */"
    parsed = auto_explain.parse_auto_explain(
        "duration: 5 ms  plan:\n"
        + '{"Query Text":'
        + json.dumps(query)
        + ',"Plan":{"Node Type":"Result"}}',
        complete=True,
    )
    assert parsed is not None
    assert parsed.query_sample is not None
    assert "secret" not in parsed.query_sample
    assert "[REDACTED]" in parsed.query_sample
    assert len(parsed.query_sample) == 303
    assert parsed.query_sample.endswith("...")
    assert parsed.viewer_plan is not None
    assert "secret" not in parsed.viewer_plan
    assert "[REDACTED]" in parsed.viewer_plan


def test_parse_auto_explain_json_viewer_stays_valid_after_sanitization() -> None:
    body = json.dumps(
        {
            "Query Text": "SELECT * FROM movie_keyword mk JOIN keyword k "
            "ON mk.keyword_id = k.id",
            "Plan": {
                "Node Type": "Hash Join",
                "Hash Cond": "(mk.keyword_id = k.id)",
            },
        },
        indent=2,
    )
    parsed = auto_explain.parse_auto_explain(f"duration: 199.989 ms  plan:\n{body}", complete=True)

    assert parsed is not None
    assert parsed.viewer_plan is not None
    _, viewer_json = parsed.viewer_plan.split("\n", 1)
    viewer_payload = json.loads(viewer_json)
    assert viewer_payload["Plan"]["Node Type"] == "Hash Join"
    assert "[REDACTED]" in viewer_payload["Plan"]["Hash Cond"]


@pytest.mark.parametrize("plan_format", ["json", "xml"])
def test_parse_auto_explain_deep_plan_does_not_abort_log_phase(plan_format: str) -> None:
    if plan_format == "json":
        plan = '{"Node Type":"Result"}'
        for _ in range(500):
            plan = '{"Node Type":"Subquery Scan","Plans":[' + plan + "]}"
        body = '{"Query Text":"select 1","Plan":' + plan + "}"
    else:
        plan = "<Plan><Node-Type>Result</Node-Type></Plan>"
        for _ in range(800):
            plan = "<Plan><Node-Type>Subquery Scan</Node-Type><Plans>" + plan + "</Plans></Plan>"
        body = "<explain><Query><Query-Text>select 1</Query-Text>" + plan + "</Query></explain>"

    parsed = auto_explain.parse_auto_explain(f"duration: 1 ms  plan:\n{body}", complete=True)

    assert parsed is not None
    assert parsed.parsed
    assert parsed.node_count > 500
    assert parsed.viewer_plan is None


def test_parse_auto_explain_json_recursion_fallback_preserves_metadata(monkeypatch) -> None:
    body = json.dumps(
        {
            "Query Text": "select * from accounts where password = 'secret'",
            "Plan": {
                "Node Type": "Subquery Scan",
                "Plans": [{"Node Type": "Result"}],
            },
        }
    )

    def raise_recursion_error(_value: str):
        raise RecursionError

    monkeypatch.setattr(auto_explain.json, "loads", raise_recursion_error)
    parsed = auto_explain.parse_auto_explain(f"duration: 1 ms  plan:\n{body}", complete=True)

    assert parsed is not None
    assert parsed.parsed
    assert parsed.root_node_type == "Subquery Scan"
    assert parsed.node_count == 2
    assert parsed.query_sample is not None
    assert "secret" not in parsed.query_sample
    assert "[REDACTED]" in parsed.query_sample
    assert parsed.viewer_plan is None


# --- physical RLE ---


def _line(lineno_marker: str, tail: str) -> bytes:
    prefix = f"2026-08-31 10:00:0{lineno_marker} UTC,u,d,1,c,s,{lineno_marker},t,st,v,x"
    return f"{prefix},{tail}".encode()


def test_strip_prefix_quote_aware() -> None:
    line = b'ts,"we,ird",db,1,c,s,7,"say ""hi""",st,v,x,ERROR,42601,msg'
    assert rle.strip_prefix(line) == b"ERROR,42601,msg"
    assert rle.strip_prefix(b"no commas here") is None


def test_physical_rle_adjacent_only() -> None:
    collapsed = rle.PhysicalRle("f.csv", raw_record_cap=8192)
    out: list[RawSeries] = []
    # matched lines at physical positions 1, 3: NOT adjacent -> two series
    for lineno, tail in ((1, "ERROR,x,same"), (3, "ERROR,x,same")):
        emitted = collapsed.feed(lineno, _line(str(lineno), tail))
        if emitted:
            out.append(emitted)
    tail_series = collapsed.flush()
    assert tail_series is not None
    out.append(tail_series)
    assert [series.count for series in out] == [1, 1]


def test_physical_rle_collapses_adjacent_identical() -> None:
    collapsed = rle.PhysicalRle("f.csv", raw_record_cap=8192)
    out = []
    for lineno in (5, 6, 7):
        emitted = collapsed.feed(lineno, _line("9", "ERROR,x,flood"))
        if emitted:
            out.append(emitted)
    out.append(collapsed.flush())
    assert len(out) == 1
    assert out[0].count == 3
    assert out[0].first_lineno == 5
    assert out[0].last_lineno == 7


def test_physical_rle_raw_cap_flag() -> None:
    collapsed = rle.PhysicalRle("f.csv", raw_record_cap=32)
    emitted = collapsed.feed(1, _line("1", "ERROR,x," + "y" * 100))
    assert emitted is None
    series = collapsed.flush()
    assert series is not None
    assert series.raw_truncated
    assert len(series.raw_record) == 32


def test_physical_rle_never_merges_auto_explain_records() -> None:
    collapsed = rle.PhysicalRle("f.csv", raw_record_cap=8192)
    line = _line("9", 'LOG,00000,"duration: 10 ms  plan:\nResult  (cost=0..1)"')
    assert collapsed.feed(1, line) is None
    emitted = collapsed.feed(2, line)
    assert emitted is not None
    assert emitted.count == 1
    tail = collapsed.flush()
    assert tail is not None
    assert tail.count == 1


def test_physical_rle_does_not_merge_different_identities() -> None:
    collapsed = rle.PhysicalRle("f.csv", raw_record_cap=8192)
    alice = b"ts1,alice,db1,11,10.0.0.1:1,s1,1,SEL,st,3/4,778,ERROR,42601,boom"
    bob = b"ts2,bob,db2,22,10.0.0.2:2,s2,1,SEL,st,3/5,779,ERROR,42601,boom"
    assert collapsed.feed(1, alice) is None
    emitted = collapsed.feed(2, bob)  # same tail, different user -> new series
    assert emitted is not None
    assert emitted.count == 1


def test_fingerprint_long_prefix_not_merged() -> None:
    assert rle.fingerprint("A" * 200 + " X") != rle.fingerprint("A" * 200 + " Y")


def test_sanitize_bearer_basic_aws_and_quoted_values() -> None:
    leaks = ("supersecret", "dXNlcjpwYXNz", "AKIAIOSFODNN7EXAMPLE", "qsecret")
    cases = [
        "Authorization: Bearer supersecret",
        "authorization=Basic dXNlcjpwYXNz",
        "found key AKIAIOSFODNN7EXAMPLE in env",
        'api_key="qsecret"',
    ]
    for case in cases:
        out = sanitize.sanitize_text(case)
        assert not any(leak in out for leak in leaks), out


def test_fingerprint_normalizes_numbers_and_space() -> None:
    left = rle.fingerprint("duplicate key 42   in table t99")
    right = rle.fingerprint("duplicate key 7 in table t1")
    assert left == right


def test_sanitize_composite_secret_names() -> None:
    leaks = ("VerySecretValue123", "hunter2", "abc123DEF", "zz9")
    cases = [
        "aws_secret_access_key=VerySecretValue123",
        "client_secret: hunter2",
        "refresh_token=abc123DEF",
        "DB_PASSWORD=zz9",
    ]
    for case in cases:
        out = sanitize.sanitize_text(case)
        assert not any(leak in out for leak in leaks), out
    # prose that must survive untouched
    assert sanitize.sanitize_text("duplicate key value violates constraint") == (
        "duplicate key value violates constraint"
    )


def test_auth_recall_catches_sqlstate_variants() -> None:
    from pg_diag.logscan.item_recall import ITEM_RECALL

    clauses = ITEM_RECALL["server_log.authentication_failures"]
    pam_line = b"ts,u,db,1,c,s,7,,st,v,x,FATAL,28P01,PAM authentication failed for user"
    assert recall.matches(pam_line, clauses)
