"""Unit tests for the pure logscan layers: recall, sanitize, csvparse, rle."""

from __future__ import annotations

import pytest

from pg_diag.logscan import csvparse, recall, rle, sanitize
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
