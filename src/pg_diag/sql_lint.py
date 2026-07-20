"""Static SQL linting for diagnostic query files."""

from __future__ import annotations

import re
from dataclasses import dataclass


READ_ONLY_START = {"select", "with", "show", "values", "explain"}
BANNED_STATEMENTS = {
    "insert",
    "update",
    "delete",
    "merge",
    "create",
    "alter",
    "drop",
    "truncate",
    "vacuum",
    "analyze",
    "reindex",
    "cluster",
    "grant",
    "revoke",
    "copy",
    "call",
    "do",
}


@dataclass(frozen=True)
class SqlLintIssue:
    code: str
    message: str


def _mask_comments_and_literals(sql: str) -> str:
    result: list[str] = []
    i = 0
    state = "normal"
    dollar_tag = ""
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""

        if state == "normal":
            if ch == "-" and nxt == "-":
                result.extend("  ")
                i += 2
                state = "line_comment"
                continue
            if ch == "/" and nxt == "*":
                result.extend("  ")
                i += 2
                state = "block_comment"
                continue
            if ch == "'":
                result.append(" ")
                i += 1
                state = "single_quote"
                continue
            if ch == '"':
                result.append(" ")
                i += 1
                state = "double_quote"
                continue
            if ch == "$":
                match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql[i:])
                if match:
                    dollar_tag = match.group(0)
                    result.extend(" " * len(dollar_tag))
                    i += len(dollar_tag)
                    state = "dollar_quote"
                    continue
            result.append(ch)
            i += 1
            continue

        if state == "line_comment":
            result.append("\n" if ch == "\n" else " ")
            i += 1
            if ch == "\n":
                state = "normal"
            continue

        if state == "block_comment":
            if ch == "*" and nxt == "/":
                result.extend("  ")
                i += 2
                state = "normal"
            else:
                result.append("\n" if ch == "\n" else " ")
                i += 1
            continue

        if state == "single_quote":
            if ch == "'" and nxt == "'":
                result.extend("  ")
                i += 2
                continue
            result.append("\n" if ch == "\n" else " ")
            i += 1
            if ch == "'":
                state = "normal"
            continue

        if state == "double_quote":
            if ch == '"' and nxt == '"':
                result.extend("  ")
                i += 2
                continue
            result.append("\n" if ch == "\n" else " ")
            i += 1
            if ch == '"':
                state = "normal"
            continue

        if state == "dollar_quote":
            if sql.startswith(dollar_tag, i):
                result.extend(" " * len(dollar_tag))
                i += len(dollar_tag)
                state = "normal"
            else:
                result.append("\n" if ch == "\n" else " ")
                i += 1
            continue

    return "".join(result)


def _has_multiple_top_level_statements(masked: str) -> bool:
    depth = 0
    saw_statement_end = False
    for ch in masked:
        if ch == "(":
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
        elif ch == ";" and depth == 0:
            saw_statement_end = True
        elif saw_statement_end and not ch.isspace():
            return True
    return False


def lint_sql(sql: str) -> list[SqlLintIssue]:
    issues: list[SqlLintIssue] = []
    masked = _mask_comments_and_literals(sql)
    stripped = masked.strip()
    if not stripped:
        return [SqlLintIssue("empty_sql", "SQL file is empty")]

    if _has_multiple_top_level_statements(masked):
        issues.append(SqlLintIssue("multi_statement", "SQL must contain one top-level statement"))

    first = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", stripped)
    if not first:
        issues.append(SqlLintIssue("unknown_statement", "Cannot determine SQL statement type"))
        return issues

    first_keyword = first.group(1).lower()
    if first_keyword not in READ_ONLY_START:
        issues.append(
            SqlLintIssue(
                "not_read_only",
                f"SQL statement must start with a read-only keyword, got {first_keyword!r}",
            )
        )

    for keyword in sorted(BANNED_STATEMENTS):
        if re.search(rf"\b{re.escape(keyword)}\b", masked, flags=re.IGNORECASE):
            issues.append(
                SqlLintIssue("banned_statement", f"SQL contains banned statement keyword {keyword!r}")
            )

    if first_keyword == "explain" and re.search(r"\banalyze\b", masked, flags=re.IGNORECASE):
        issues.append(SqlLintIssue("explain_analyze", "EXPLAIN ANALYZE is not allowed"))

    return issues
