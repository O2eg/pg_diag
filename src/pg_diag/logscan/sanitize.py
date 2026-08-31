"""Sanitizer for log message text (plan §5).

Applied on the collector before fingerprinting, client RLE, and the artifact.
Truncation to LINE_CAP is a display concern and must happen only after this.
"""

from __future__ import annotations

import re

REDACTED = "[REDACTED]"
LITERAL = "'[LITERAL]'"

# Order matters: structured secrets first (explicit marker), generic quoted
# literals last. The value alternatives must cover quoted values and schemes
# like ``Authorization: Bearer <token>`` where the secret is the SECOND word
# (review finding, 2026-08-31).
_VALUE = r"(?:\"[^\"]*\"|'(?:[^']|'')*'|[^\s,;]+)"

_PASSWORD_LITERAL_RE = re.compile(r"(?i)\b(password)\s+('(?:[^']|'')*')")
_AUTH_SCHEME_RE = re.compile(
    rf"(?i)\b(authorization|proxy-authorization)\s*[=:]\s*(?:(bearer|basic|token|negotiate|digest)\s+)?{_VALUE}"
)
_BEARER_RE = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")
# Composite names (aws_secret_access_key, client_secret, refresh_token) must
# match too, so the stem may sit anywhere inside the identifier; over-redaction
# is the safe direction for a log sanitizer (review finding, 2026-08-31).
_KEY_VALUE_SECRET_RE = re.compile(
    rf"(?i)\b([A-Za-z0-9_-]*(?:password|passwd|pwd|secret|token|credential|key)"
    rf"[A-Za-z0-9_-]*)\s*[=:]\s*{_VALUE}"
)
_AWS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
_URI_CREDENTIALS_RE = re.compile(r"(?i)(://[^/\s:@']+:)([^@\s/']+)(@)")
_QUOTED_LITERAL_RE = re.compile(r"'(?:[^']|'')*'")


def sanitize_text(text: str) -> str:
    """Redact secrets and replace quoted literals with placeholders."""
    text = _PASSWORD_LITERAL_RE.sub(rf"\1 {REDACTED}", text)
    text = _AUTH_SCHEME_RE.sub(rf"\1={REDACTED}", text)
    text = _BEARER_RE.sub(rf"\1 {REDACTED}", text)
    text = _KEY_VALUE_SECRET_RE.sub(rf"\1={REDACTED}", text)
    text = _AWS_KEY_RE.sub(REDACTED, text)
    text = _URI_CREDENTIALS_RE.sub(rf"\g<1>{REDACTED}\g<3>", text)
    text = _QUOTED_LITERAL_RE.sub(LITERAL, text)
    return text
