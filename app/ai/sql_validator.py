"""SQL safety validator for LLM-generated SQL (Layer 2 of 3).

Layer 1: PostgreSQL role `analytics_ro` has SELECT-only grants, read-only
         sessions and a statement timeout (database/init/02_readonly_role.sh).
Layer 2: this module PARSES the SQL into a syntax tree with sqlglot and checks
         the tree - not just keywords - so tricks like comments, odd casing or
         a DELETE hidden inside a CTE are caught.
Layer 3: execution runs inside a READ ONLY transaction with a row limit.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

ALLOWED_TABLES = {"customers", "products", "orders", "order_items", "payments"}

# Statement types that must never appear anywhere in the tree.
_FORBIDDEN_NODES = tuple(
    t for t in (getattr(exp, n, None) for n in (
        "Insert", "Update", "Delete", "Drop", "Create", "Alter", "AlterTable",
        "TruncateTable", "Merge", "Command", "Grant", "Revoke", "Copy", "Set",
        "Transaction", "Commit", "Rollback", "Into", "Lock", "Use", "Pragma"))
    if isinstance(t, type)
)
# Dangerous or side-effect functions (server files, sleeping, killing sessions, settings).
_FORBIDDEN_FUNC_PREFIXES = ("pg_", "lo_", "dblink", "set_config", "current_setting",
                            "query_to_xml", "txid_", "nextval", "setval")


@dataclass
class ValidationResult:
    is_valid: bool
    sql: str = ""                      # safe SQL to execute (with LIMIT)
    errors: list[str] = field(default_factory=list)


def _func_name(node: exp.Expression) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.name).lower()
    try:
        return node.sql_name().lower()
    except Exception:  # noqa: BLE001
        return type(node).__name__.lower()


def validate_sql(sql: str, max_rows: int = 200) -> ValidationResult:
    errors: list[str] = []
    if not sql or not sql.strip():
        return ValidationResult(False, errors=["Empty SQL."])
    cleaned = sql.strip().rstrip(";").strip()

    # 1) Parse. Unparseable SQL is rejected (we never execute what we can't inspect).
    try:
        statements = [s for s in sqlglot.parse(cleaned, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as e:
        return ValidationResult(False, errors=[f"SQL could not be parsed: {str(e).splitlines()[0]}"])

    # 2) Exactly one statement ("SELECT 1; DROP TABLE x" is two).
    if len(statements) != 1:
        return ValidationResult(False, errors=[f"Exactly one statement allowed, found {len(statements)}."])
    tree = statements[0]

    # 3) Root must be a SELECT (a WITH ... SELECT parses as Select) or UNION/INTERSECT/EXCEPT.
    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        errors.append(f"Only SELECT queries are allowed (got {type(tree).__name__.upper()}).")

    # 4) Walk EVERY node: no write/DDL nodes anywhere (including inside CTEs/subqueries).
    for node in tree.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            errors.append(f"Forbidden operation: {type(node).__name__.upper()}.")
        if isinstance(node, exp.Func):
            name = _func_name(node)
            if name.startswith(_FORBIDDEN_FUNC_PREFIXES):
                errors.append(f"Forbidden function: {name}().")

    # 5) Only our 5 business tables (or CTE names defined in the query) may be read.
    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    for t in tree.find_all(exp.Table):
        name = t.name.lower()
        if t.args.get("db") or t.args.get("catalog"):
            schema = str(t.args.get("db") or "").lower()
            if schema not in ("", "public"):
                errors.append(f"Access to schema '{schema}' is not allowed.")
        if name and name not in ALLOWED_TABLES and name not in cte_names:
            errors.append(f"Table '{name}' is not allowed.")

    # Note: no plain keyword blacklist - "DROP" inside a string literal is harmless,
    # and the parse tree above already tells us exactly what the query does.
    if errors:
        return ValidationResult(False, errors=sorted(set(errors)))

    # 7) Enforce a row LIMIT.
    limit = tree.args.get("limit")
    if isinstance(tree, exp.Select):
        current = None
        if limit is not None:
            try:
                current = int(limit.expression.name)
            except Exception:  # noqa: BLE001
                current = None
        if current is None or current > max_rows:
            tree = tree.limit(max_rows)
        safe_sql = tree.sql(dialect="postgres", pretty=True)
    else:  # set operations: wrap
        safe_sql = f"SELECT * FROM (\n{tree.sql(dialect='postgres', pretty=True)}\n) AS q LIMIT {max_rows}"

    return ValidationResult(True, sql=safe_sql)
