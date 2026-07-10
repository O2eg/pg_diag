from __future__ import annotations

from _local_security_common import *


async def collect(ctx: PythonSourceContext) -> PythonSourceResult:
    del ctx
    def inspect() -> tuple[list[dict[str, Any]], bool, int]:
        rows = []
        read_any = False
        unreadable_count = 0
        for path in _sudoers_files():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except PermissionError:
                unreadable_count += 1
                continue
            except OSError:
                continue
            read_any = True
            for line_number, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                lower = stripped.lower()
                if "postgres" not in lower:
                    continue
                all_token = re.search(r"(^|[\s,:=()])all($|[\s,:=()])", lower)
                risky = "nopasswd" in lower or all_token or re.search(r"(^|/)(su|sudo|bash|sh)\b", lower)
                if risky:
                    rows.append(
                        {
                            "file_path": str(path),
                            "line_number": line_number,
                            "rule_excerpt": stripped[:240],
                            "risk_level": "high" if "nopasswd" in lower else "medium",
                            "risk_reason": "sudoers rule may allow broad escalation to or from the postgres OS account",
                        }
                    )
        return rows, read_any, unreadable_count

    rows, read_any, unreadable_count = await run_blocking(inspect)
    if not read_any:
        return _unavailable_result(
            "The collector cannot read any sudoers evidence to verify postgres escalation rules",
            "security_sudoers_permission",
        )
    return _result(
        rows,
        ok_title="No broad sudoers postgres escalation rules found",
        fail_title="sudoers postgres escalation findings found",
        recommendation="Avoid passwordless broad sudo access involving the postgres OS account; restrict commands to audited maintenance wrappers.",
        diagnostic_code="security_sudoers_postgres_escalation",
        coverage_complete=unreadable_count == 0,
        coverage_note=(
            f"{unreadable_count} sudoers file(s) could not be read"
            if unreadable_count else ""
        ),
    )
