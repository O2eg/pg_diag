"""Read-only DDL extraction for PostgreSQL 10+ (a client-side pgddl port).

Logic ported from the lacanoid/pgddl extension (PostgreSQL licence,
https://github.com/lacanoid/pgddl) and cross-checked against pg_dump.
Unlike the extension, nothing is ever installed or created in the observed
database: the extractor runs bounded catalog SELECTs and assembles the DDL
text in Python.
"""

from pg_diag.ddlx.extract import DdlExtractor, ObjectDdl, TableBundle

__all__ = ["DdlExtractor", "ObjectDdl", "TableBundle"]
