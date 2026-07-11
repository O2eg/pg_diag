"""Shared exceptions for pg_diag."""

from __future__ import annotations


class PgDiagError(Exception):
    """Base class for user-facing pg_diag errors."""


class CommandTimeoutError(PgDiagError):
    """A bounded local or remote host command exceeded its deadline."""


class ContentLoadError(PgDiagError):
    """Raised when content files cannot be loaded."""


class ValidationError(PgDiagError):
    """Raised when content validation fails."""


class UnsupportedServerVersion(PgDiagError):
    """Raised when a PostgreSQL server version is outside the support window."""
