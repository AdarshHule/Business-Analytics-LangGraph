"""Schema, constraints, data volume and financial consistency checks."""
import pytest
from sqlalchemy import text

from app.database import get_constraints, run_query

TABLES = ["customers", "products", "orders", "order_items", "payments"]


def test_five_tables_exist(engine):
    df = run_query("SELECT table_name FROM information_schema.tables WHERE table_schema='public' "
                   "AND table_type='BASE TABLE'")
    assert sorted(df.table_name) == sorted(TABLES)


def test_primary_keys(engine):
    pks = get_constraints().query("constraint_type == 'PRIMARY KEY'")
    assert sorted(pks.table_name) == sorted(TABLES)


def test_foreign_keys(engine):
    fks = get_constraints().query("constraint_type == 'FOREIGN KEY'")
    defs = set(fks.table_name + ":" + fks.definition)
    assert "orders:FOREIGN KEY (customer_id) REFERENCES customers(customer_id)" in defs
    assert any(d.startswith("order_items:FOREIGN KEY (order_id) REFERENCES orders(order_id)") for d in defs)
    assert "order_items:FOREIGN KEY (product_id) REFERENCES products(product_id)" in defs
    assert any(d.startswith("payments:FOREIGN KEY (order_id) REFERENCES orders(order_id)") for d in defs)


def test_minimum_volumes(engine):
    c = run_query("""SELECT (SELECT COUNT(*) FROM customers) c, (SELECT COUNT(*) FROM products) p,
                            (SELECT COUNT(*) FROM orders) o, (SELECT COUNT(*) FROM order_items) i,
                            (SELECT COUNT(*) FROM payments) pay,
                            (SELECT COUNT(DISTINCT category) FROM products) cats,
                            (SELECT COUNT(DISTINCT city) FROM customers) cities,
                            (SELECT COUNT(DISTINCT date_trunc('month', order_date)) FROM orders) months""").iloc[0]
    assert c.c >= 100 and c.p >= 20 and c.o >= 300 and c.i > c.o and c.pay >= c.o
    assert c.cats >= 3 and c.cities >= 5 and c.months >= 3


def test_no_orphans(engine):
    r = run_query("""SELECT
        (SELECT COUNT(*) FROM orders o LEFT JOIN customers c USING (customer_id) WHERE c.customer_id IS NULL) a,
        (SELECT COUNT(*) FROM order_items i LEFT JOIN orders o USING (order_id) WHERE o.order_id IS NULL) b,
        (SELECT COUNT(*) FROM orders o WHERE NOT EXISTS (SELECT 1 FROM order_items i WHERE i.order_id=o.order_id)) c,
        (SELECT COUNT(*) FROM orders o WHERE NOT EXISTS (SELECT 1 FROM payments p WHERE p.order_id=o.order_id)) d""").iloc[0]
    assert (r.a, r.b, r.c, r.d) == (0, 0, 0, 0)


def test_order_total_equals_sum_of_items(engine):
    n = run_query("""SELECT COUNT(*) n FROM orders o
                     WHERE o.total_amount <> (SELECT SUM(subtotal) FROM order_items i WHERE i.order_id=o.order_id)""").n[0]
    assert n == 0


def test_revenue_equals_successful_payments(engine):
    r = run_query("""SELECT
        (SELECT SUM(total_amount) FROM orders WHERE order_status IN ('processing','shipped','delivered')) rev,
        (SELECT SUM(amount) FROM payments WHERE payment_status='success') paid,
        (SELECT COUNT(*) FROM (SELECT order_id FROM payments WHERE payment_status='success'
                               GROUP BY 1 HAVING COUNT(*)>1) x) dup""").iloc[0]
    assert float(r.rev) == float(r.paid)
    assert r.dup == 0     # never more than one successful payment per order


def test_readonly_role_cannot_write(engine):
    for stmt in ["INSERT INTO products(product_name,category,unit_price,cost_price,stock_quantity) "
                 "VALUES ('x','x',1,1,1)", "UPDATE products SET stock_quantity = 0",
                 "DELETE FROM payments", "DROP TABLE payments", "CREATE TABLE hack(x int)"]:
        with engine.connect() as conn:
            with pytest.raises(Exception):
                conn.execute(text(stmt))
            conn.rollback()


def test_readonly_role_cannot_escape_read_only_mode(engine):
    """Even after switching the transaction to READ WRITE, grants still block writes."""
    with engine.connect() as conn:
        conn.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE"))
        conn.commit()
        with pytest.raises(Exception, match="permission denied"):
            conn.execute(text("DELETE FROM payments"))
        conn.rollback()
    assert run_query("SELECT COUNT(*) n FROM payments").n[0] > 0


def test_statement_timeout(engine):
    with engine.connect() as conn:
        with pytest.raises(Exception, match="statement timeout"):
            conn.execute(text("SELECT pg_sleep(7)"))
