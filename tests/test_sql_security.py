"""The validator must reject every write/DDL/escape attempt and allow normal analytics SQL."""
import pytest

from app.ai.sql_validator import validate_sql

SAFE = [
    "SELECT * FROM customers",
    "SELECT city, COUNT(*) AS n FROM customers GROUP BY city ORDER BY n DESC LIMIT 5",
    "WITH m AS (SELECT date_trunc('month', order_date) AS m, SUM(total_amount) AS r FROM orders GROUP BY 1) "
    "SELECT * FROM m ORDER BY m",
    "SELECT p.category, SUM(oi.subtotal) FROM order_items oi JOIN products p ON p.product_id = oi.product_id GROUP BY 1",
    "SELECT * FROM customers WHERE customer_name = 'x''; DROP TABLE orders; --'",   # just a string literal
    "SELECT city FROM customers UNION SELECT category FROM products",
]

ATTACKS = [
    "DELETE FROM payments",
    "DROP TABLE orders",
    "UPDATE products SET unit_price = 0",
    "INSERT INTO customers VALUES (999, 'x', 'x@x.com', 'x', 'x', '2026-01-01')",
    "TRUNCATE orders",
    "ALTER TABLE orders ADD COLUMN hacked int",
    "SELECT 1; DROP TABLE orders",
    "SeLeCt * FROM orders /* hi */ ; dElEtE FROM orders",
    "WITH x AS (DELETE FROM orders RETURNING *) SELECT * FROM x",
    "SELECT pg_sleep(10)",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT * FROM pg_shadow",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM pg_catalog.pg_roles",
    "SELECT * INTO stolen FROM customers",
    "SELECT * FROM orders FOR UPDATE",
    "GRANT ALL ON orders TO PUBLIC",
    "COPY customers TO '/tmp/customers.csv'",
    "SET statement_timeout = 0",
    "BEGIN READ WRITE",
    "SELECT set_config('default_transaction_read_only', 'off', false)",
    "CREATE TABLE hack AS SELECT * FROM customers",
    "",
]


@pytest.mark.parametrize("sql", SAFE)
def test_safe_queries_allowed(sql):
    r = validate_sql(sql)
    assert r.is_valid, r.errors
    assert "LIMIT" in r.sql.upper()


@pytest.mark.parametrize("sql", ATTACKS)
def test_attacks_rejected(sql):
    r = validate_sql(sql)
    assert not r.is_valid
    assert r.errors


def test_limit_is_capped():
    r = validate_sql("SELECT * FROM orders LIMIT 100000", max_rows=200)
    assert r.is_valid and r.sql.rstrip().endswith("LIMIT 200")


def test_small_limit_is_kept():
    r = validate_sql("SELECT * FROM orders LIMIT 5", max_rows=200)
    assert r.sql.rstrip().endswith("LIMIT 5")
