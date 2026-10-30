"""Dashboard query correctness: cross-check aggregations with independent SQL."""
from datetime import date

from app import queries as q
from app.database import run_query

ALL = q.Filters(date(2026, 1, 1), date(2026, 12, 31))


def test_kpis_match_independent_sql(engine):
    k = q.kpis(ALL)
    ref = run_query("""SELECT SUM(total_amount) rev, COUNT(*) n FROM orders
                       WHERE order_status IN ('processing','shipped','delivered')""").iloc[0]
    assert round(k["revenue"], 2) == round(float(ref.rev), 2)
    assert k["revenue_orders"] == ref.n
    assert k["total_orders"] == run_query("SELECT COUNT(*) n FROM orders").n[0]
    assert abs(k["aov"] - float(ref.rev) / ref.n) < 0.01
    assert abs(k["gross_profit"] - (k["revenue"] - k["cogs"])) < 0.01
    assert 0 < k["margin"] < 1


def test_successful_payments_equal_revenue(engine):
    assert round(q.successful_payments_total(ALL), 2) == round(q.kpis(ALL)["revenue"], 2)


def test_breakdowns_sum_to_total(engine):
    total = q.kpis(ALL)["revenue"]
    assert abs(q.monthly_revenue(ALL).revenue.astype(float).sum() - total) < 0.01
    assert abs(q.revenue_by_category(ALL).revenue.astype(float).sum() - total) < 0.01
    assert abs(q.revenue_by_city(ALL).revenue.astype(float).sum() - total) < 0.01
    assert abs(q.repeat_customers(ALL).revenue.astype(float).sum() - total) < 0.01


def test_filters_reduce_results(engine):
    f = q.Filters(date(2026, 9, 1), date(2026, 9, 30), ("Electronics",), ("Pune",))
    k = q.kpis(f)
    ref = run_query("""SELECT COALESCE(SUM(oi.subtotal),0) r FROM order_items oi
        JOIN orders o USING (order_id) JOIN customers c USING (customer_id) JOIN products p USING (product_id)
        WHERE o.order_status IN ('processing','shipped','delivered') AND o.order_date BETWEEN '2026-09-01' AND '2026-09-30'
          AND p.category='Electronics' AND c.city='Pune'""").r[0]
    assert round(k["revenue"], 2) == round(float(ref), 2)
    assert k["revenue"] < q.kpis(ALL)["revenue"]


def test_top_products_ordering(engine):
    df = q.top_products(ALL, "revenue", 10)
    assert len(df) == 10
    assert list(df.revenue) == sorted(df.revenue, reverse=True)


def test_order_status_counts(engine):
    assert q.orders_by_status(ALL).orders.sum() == run_query("SELECT COUNT(*) n FROM orders").n[0]


def test_payment_method_counts(engine):
    assert q.payments_by_method(ALL).attempts.sum() == run_query("SELECT COUNT(*) n FROM payments").n[0]


def test_insights_generated_from_data(engine):
    from app.insights import build_insights
    ins = build_insights()
    assert len(ins) >= 5
    for i in ins:
        assert i["finding"] and i["meaning"] and i["action"] and len(i["data"]) > 0
