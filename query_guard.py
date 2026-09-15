"""Validation and safety policy for model-generated SQL."""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp


class UnsafeQueryError(ValueError):
    """Raised when generated SQL violates the read-only query policy."""


_FENCED_SQL = re.compile(r"^```(?:sql)?\s*(.*?)\s*```$", re.IGNORECASE | re.DOTALL)
_BLOCKED_KEYWORDS = {"ALTER", "ATTACH", "CREATE", "DELETE", "DETACH", "DROP", "GRANT", "INSERT", "REPLACE", "REVOKE", "TRUNCATE", "UPDATE"}
_BLOCKED_PATTERNS = (r"\bINTO\s+(?:OUTFILE|DUMPFILE)\b", r"\bFOR\s+UPDATE\b", r"\b(?:BENCHMARK|LOAD_FILE|SLEEP)\s*\(")


def validate_read_only_sql(sql: str, *, max_rows: int = 100) -> str:
    """Return normalized read-only SQL or raise ``UnsafeQueryError``."""
    candidate = (sql or "").strip()
    fenced = _FENCED_SQL.match(candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    if not candidate:
        raise UnsafeQueryError("The model returned an empty SQL query.")
    if ";" in candidate.rstrip(";"):
        raise UnsafeQueryError("Multiple SQL statements are not allowed.")
    try:
        statement = sqlglot.parse_one(candidate, read="mysql")
    except sqlglot.errors.ParseError as exc:
        raise UnsafeQueryError("The generated SQL could not be parsed.") from exc
    if not isinstance(statement, (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.With)):
        raise UnsafeQueryError("Only read-only SELECT queries are allowed.")
    upper_sql = candidate.upper()
    if any(re.search(rf"\b{keyword}\b", upper_sql) for keyword in _BLOCKED_KEYWORDS):
        raise UnsafeQueryError("The generated SQL contains a blocked operation.")
    if any(re.search(pattern, upper_sql) for pattern in _BLOCKED_PATTERNS):
        raise UnsafeQueryError("The generated SQL contains a blocked operation.")
    if max_rows < 1:
        raise ValueError("max_rows must be positive")
    limit = statement.args.get("limit")
    if limit and isinstance(limit.expression, exp.Literal) and limit.expression.is_number:
        if int(limit.expression.this) > max_rows:
            statement = statement.limit(max_rows)
    elif limit and not isinstance(limit.expression, exp.Literal):
        raise UnsafeQueryError("The row limit must be a numeric constant.")
    if not limit:
        statement = statement.limit(max_rows)
    return statement.sql(dialect="mysql")
