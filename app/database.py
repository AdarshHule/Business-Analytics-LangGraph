"""Database access layer: one SQLAlchemy engine, one helper that returns DataFrames.

Every query in the app goes through run_query(), using the READ-ONLY role.
Parameters are always passed separately (bound parameters), never pasted
into SQL strings -> this is what prevents SQL injection from filter values.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine

from app import config


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = URL.create(
        "postgresql+psycopg",
        username=config.RO_DB_USER,
        password=config.RO_DB_PASSWORD,
        host=config.DB_HOST,
        port=config.DB_PORT,
        database=config.DB_NAME,
    )
    # Belt and braces: the role already has these settings in PostgreSQL,
    # we set them again per connection.
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        connect_args={
            "options": f"-c default_transaction_read_only=on "
                       f"-c statement_timeout={config.STATEMENT_TIMEOUT_MS}",
            "connect_timeout": 5,
        },
    )


def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def ping() -> tuple[bool, str]:
    """Used by the UI to show a friendly message if the database is down."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "connected"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc).splitlines()[0]


TABLES = ["customers", "products", "orders", "order_items", "payments"]


def get_columns() -> pd.DataFrame:
    """Live schema from PostgreSQL's catalog (information_schema) - not hardcoded."""
    return run_query("""
        SELECT c.table_name, c.column_name, c.data_type,
               COALESCE(c.character_maximum_length::text,
                        CASE WHEN c.numeric_precision IS NOT NULL AND c.data_type='numeric'
                             THEN c.numeric_precision || ',' || c.numeric_scale END) AS size,
               c.is_nullable, c.ordinal_position
        FROM information_schema.columns c
        WHERE c.table_schema = 'public' AND c.table_name = ANY(:t)
        ORDER BY array_position(:t, c.table_name::text), c.ordinal_position
    """, {"t": TABLES})


def get_constraints() -> pd.DataFrame:
    """PK / FK / UNIQUE / CHECK constraints with readable definitions."""
    return run_query("""
        SELECT rel.relname AS table_name, con.conname AS constraint_name,
               CASE con.contype WHEN 'p' THEN 'PRIMARY KEY' WHEN 'f' THEN 'FOREIGN KEY'
                                WHEN 'u' THEN 'UNIQUE' WHEN 'c' THEN 'CHECK' END AS constraint_type,
               pg_get_constraintdef(con.oid) AS definition
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = rel.relnamespace
        WHERE n.nspname = 'public' AND rel.relname = ANY(:t)
        ORDER BY array_position(:t, rel.relname::text), con.contype DESC, con.conname
    """, {"t": TABLES})


def get_row_counts() -> pd.DataFrame:
    return run_query("""
        SELECT 'customers' AS table_name, COUNT(*) AS row_count FROM customers
        UNION ALL SELECT 'products', COUNT(*) FROM products
        UNION ALL SELECT 'orders', COUNT(*) FROM orders
        UNION ALL SELECT 'order_items', COUNT(*) FROM order_items
        UNION ALL SELECT 'payments', COUNT(*) FROM payments
    """)


def get_table_comments() -> dict[str, str]:
    df = run_query("""
        SELECT c.relname AS table_name, obj_description(c.oid) AS comment
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname = ANY(:t)
    """, {"t": TABLES})
    return dict(zip(df.table_name, df.comment))


def sample_rows(table: str, n: int = 10) -> pd.DataFrame:
    if table not in TABLES:  # whitelist: table names cannot be bound parameters
        raise ValueError(f"Unknown table {table}")
    return run_query(f"SELECT * FROM {table} ORDER BY 1 LIMIT :n", {"n": n})


def schema_text() -> str:
    """Compact schema description given to the LLM (built from the live catalog)."""
    cols = get_columns()
    cons = get_constraints()
    lines = []
    for t in TABLES:
        c = cols[cols.table_name == t]
        col_str = ", ".join(f"{r.column_name} {r.data_type}" for r in c.itertuples())
        lines.append(f"TABLE {t}({col_str})")
        for r in cons[(cons.table_name == t) & cons.constraint_type.isin(["PRIMARY KEY", "FOREIGN KEY", "CHECK"])].itertuples():
            lines.append(f"  {r.constraint_type}: {r.definition}")
    return "\n".join(lines)
