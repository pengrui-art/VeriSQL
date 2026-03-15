from typing import Tuple

import sqlglot


READ_ONLY_ROOT_KEYS = {"select", "union", "except", "intersect"}
MUTATING_KEYS = {
    "insert",
    "update",
    "delete",
    "create",
    "drop",
    "alter",
    "merge",
    "truncate",
    "command",
    "copy",
    "use",
    "transaction",
}


def validate_read_only_sql(sql: str, dialect: str = "sqlite") -> Tuple[bool, str]:
    """
    Accept only a single read-only query statement.

    The benchmark and verification pipeline are designed for SELECT-style Text-to-SQL
    outputs, so mutating statements are blocked even if they are syntactically valid.
    """
    text = (sql or "").strip()
    if not text:
        return False, "No SQL to execute"

    try:
        statements = sqlglot.parse(text, dialect=dialect)
    except Exception as exc:
        return False, f"SQL parse error: {exc}"

    if len(statements) != 1:
        return False, "Only a single SQL statement is allowed"

    ast = statements[0]
    if ast.key not in READ_ONLY_ROOT_KEYS:
        return False, f"Only read-only SELECT queries are allowed, got {ast.key.upper()}"

    for node in ast.walk():
        if getattr(node, "key", "") in MUTATING_KEYS:
            return False, f"Mutating SQL is not allowed: found {node.key.upper()}"

    return True, ""
