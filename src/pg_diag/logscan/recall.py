"""Recall DSL: literal-substring clauses shared by every transport.

A recall spec is a disjunction of clauses; a clause is a conjunction of literal
ASCII fragments. Literal search compiles identically to awk ``index()``, SQL
``strpos()``, and Python ``in``, so transports cannot diverge the way regex
dialects do. Precise item-level matching always happens on the collector after
CSV parsing.
"""

from __future__ import annotations

RecallClauses = tuple[tuple[bytes, ...], ...]

_MIN_FRAGMENT_LEN = 4


class RecallError(ValueError):
    """Invalid recall specification."""


def compile_clauses(clauses: list[list[str]]) -> RecallClauses:
    """Validate and normalize clauses; fragments must be printable ASCII."""
    if not clauses:
        raise RecallError("recall spec must contain at least one clause")
    compiled: list[tuple[bytes, ...]] = []
    for clause in clauses:
        if not clause:
            raise RecallError("recall clause must contain at least one fragment")
        fragments: list[bytes] = []
        for fragment in clause:
            if len(fragment) < _MIN_FRAGMENT_LEN:
                raise RecallError(f"recall fragment too short (selectivity): {fragment!r}")
            if not all(0x20 <= ord(ch) <= 0x7E for ch in fragment):
                raise RecallError(f"recall fragment must be printable ASCII: {fragment!r}")
            fragments.append(fragment.encode("ascii"))
        compiled.append(tuple(fragments))
    return tuple(compiled)


def matches(line: bytes, clauses: RecallClauses) -> bool:
    return any(all(fragment in line for fragment in clause) for clause in clauses)


def to_awk_condition(clauses: RecallClauses, variable: str = "$0") -> str:
    """Render the spec as an awk boolean expression over ``variable``."""
    rendered_clauses = []
    for clause in clauses:
        parts = [
            f'index({variable}, "{_awk_escape(fragment)}") > 0' for fragment in clause
        ]
        rendered_clauses.append("(" + " && ".join(parts) + ")")
    return " || ".join(rendered_clauses) or "0"


def _awk_escape(fragment: bytes) -> str:
    out = []
    for byte in fragment:
        ch = chr(byte)
        if ch in ('"', "\\"):
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


# Wave-1 recall set. Moves into item manifests when server_log items land;
# only enabled items are supposed to contribute clauses (plan §3).
DEFAULT_RECALL: RecallClauses = compile_clauses(
    [
        [",ERROR,"],
        [",FATAL,"],
        [",PANIC,"],
        [",WARNING,"],
        ["automatic vacuum of table"],
        ["automatic analyze of table"],
        ["checkpoint starting"],
        ["checkpoint complete"],
        ["restartpoint starting"],
        ["restartpoint complete"],
    ]
)
