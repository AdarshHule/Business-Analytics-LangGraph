"""All dashboard SQL lives here. Every number on the dashboard comes from these queries.

FINANCIAL DEFINITIONS (used consistently everywhere)
  Gross order value  = SUM(order_items.subtotal) over ALL orders, any status.
  Revenue            = SUM(order_items.subtotal) for orders with status in
                       processing / shipped / delivered (recognised sales).
                       Pending, cancelled and returned orders are excluded.
  Successful payments= SUM(payments.amount) WHERE payment_status='success'
                       (a cross-check; equals revenue in this dataset).
  Product cost (COGS)= SUM(order_items.quantity * products.cost_price) for revenue orders.
                       Assumption: current cost_price applies to past sales.
  Gross profit       = Revenue - COGS.     Profit margin = Gross profit / Revenue.

Why item level? orders.total_amount = SUM(subtotal), so revenue is identical,
but item level lets the category filter work. We never SUM payments to get
revenue because an order can have several payment rows (double counting).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from app import config
from app.database import run_query

REV = "('processing','shipped','delivered')"


@dataclass(frozen=True)
class Filters:
    start: date
    end: date
    categories: tuple[str, ...] | None = None   # None = all
    cities: tuple[str, ...] | None = None

    def params(self) -> dict:
        return {"start": self.start, "end": self.end,
                "cats": list(self.categories) if self.categories else None,
                "cities": list(self.cities) if self.cities else None}


# Item-level fact rows after applying all filters. Bound parameters only.
ITEMS_CTE = f"""
WITH f AS (
    SELECT o.order_id, o.order_date, o.order_status, o.customer_id,
           c.customer_name, c.city, c.state,
           p.product_id, p.product_name, p.category,
           oi.quantity, oi.subtotal,
           oi.quantity * p.cost_price AS item_cost,
           (o.order_status IN {REV}) AS is_revenue
    FROM order_items oi
    JOIN orders o    ON o.order_id = oi.order_id
    JOIN customers c ON c.customer_id = o.customer_id
    JOIN products p  ON p.product_id = oi.product_id
    WHERE o.order_date BETWEEN :start AND :end
      AND (CAST(:cats AS text[]) IS NULL OR p.category = ANY(CAST(:cats AS text[])))
      AND (CAST(:cities AS text[]) IS NULL OR c.city = ANY(CAST(:cities AS text[])))
)
"""

# Order-level filter (for order / payment pages). Category filter = "order contains a product in category".
ORDER_WHERE = """
    o.order_date BETWEEN :start AND :end
    AND (CAST(:cities AS text[]) IS NULL OR c.city = ANY(CAST(:cities AS text[])))
    AND (CAST(:cats AS text[]) IS NULL OR EXISTS (
         SELECT 1 FROM order_items oi JOIN products p ON p.product_id = oi.product_id
         WHERE oi.order_id = o.order_id AND p.category = ANY(CAST(:cats AS text[]))))
"""


# ---------------------------------------------------------------- filter options
def filter_options() -> dict:
    d = run_query("SELECT MIN(order_date) AS mn, MAX(order_date) AS mx FROM orders").iloc[0]
    cats = run_query("SELECT DISTINCT category FROM products ORDER BY 1").category.tolist()
    cities = run_query("SELECT DISTINCT city FROM customers ORDER BY 1").city.tolist()
    return {"min_date": d.mn, "max_date": d.mx, "categories": cats, "cities": cities}


# ---------------------------------------------------------------- executive KPIs
def kpis(f: Filters) -> dict:
    df = run_query(ITEMS_CTE + """
        SELECT
          COALESCE(SUM(subtotal) FILTER (WHERE is_revenue), 0)                 AS revenue,
          COALESCE(SUM(subtotal), 0)                                            AS gross_order_value,
          COALESCE(SUM(item_cost) FILTER (WHERE is_revenue), 0)                 AS cogs,
          COUNT(DISTINCT order_id)                                              AS total_orders,
          COUNT(DISTINCT order_id) FILTER (WHERE is_revenue)                    AS revenue_orders,
          COUNT(DISTINCT customer_id)                                           AS customers
        FROM f
    """, f.params()).iloc[0]
    revenue, cogs = float(df.revenue), float(df.cogs)
    gp = revenue - cogs
    return {
        "revenue": revenue, "gross_order_value": float(df.gross_order_value),
        "cogs": cogs, "gross_profit": gp,
        "margin": (gp / revenue) if revenue else 0.0,
        "total_orders": int(df.total_orders), "revenue_orders": int(df.revenue_orders),
        "customers": int(df.customers),
        "aov": (revenue / int(df.revenue_orders)) if int(df.revenue_orders) else 0.0,
    }


def successful_payments_total(f: Filters) -> float:
    df = run_query(f"""
        SELECT COALESCE(SUM(pay.amount),0) AS amt
        FROM payments pay JOIN orders o ON o.order_id = pay.order_id
        JOIN customers c ON c.customer_id = o.customer_id
        WHERE pay.payment_status = 'success' AND {ORDER_WHERE}
    """, f.params())
    return float(df.amt.iloc[0])


# ---------------------------------------------------------------- sales
def monthly_revenue(f: Filters) -> pd.DataFrame:
    df = run_query(ITEMS_CTE + """
        SELECT date_trunc('month', order_date)::date AS month,
               SUM(subtotal) FILTER (WHERE is_revenue)                         AS revenue,
               SUM(subtotal) FILTER (WHERE is_revenue)
                 - SUM(item_cost) FILTER (WHERE is_revenue)                    AS gross_profit,
               COUNT(DISTINCT order_id) FILTER (WHERE is_revenue)              AS orders
        FROM f GROUP BY 1 ORDER BY 1
    """, f.params())
    df = df.fillna(0)
    df["growth_pct"] = df.revenue.astype(float).pct_change() * 100
    return df


def daily_revenue(f: Filters) -> pd.DataFrame:
    return run_query(ITEMS_CTE + """
        SELECT order_date AS day, SUM(subtotal) AS revenue, COUNT(DISTINCT order_id) AS orders
        FROM f WHERE is_revenue GROUP BY 1 ORDER BY 1
    """, f.params())


def revenue_by_category(f: Filters) -> pd.DataFrame:
    return run_query(ITEMS_CTE + """
        SELECT category, SUM(subtotal) AS revenue, SUM(item_cost) AS cogs,
               SUM(subtotal) - SUM(item_cost) AS gross_profit,
               ROUND(100 * (SUM(subtotal) - SUM(item_cost)) / NULLIF(SUM(subtotal),0), 1) AS margin_pct,
               SUM(quantity) AS units
        FROM f WHERE is_revenue GROUP BY 1 ORDER BY revenue DESC
    """, f.params())


def revenue_by_city(f: Filters) -> pd.DataFrame:
    return run_query(ITEMS_CTE + """
        SELECT city, state, SUM(subtotal) AS revenue, COUNT(DISTINCT order_id) AS orders,
               COUNT(DISTINCT customer_id) AS customers
        FROM f WHERE is_revenue GROUP BY 1, 2 ORDER BY revenue DESC
    """, f.params())


def monthly_revenue_by_category(f: Filters) -> pd.DataFrame:
    return run_query(ITEMS_CTE + """
        SELECT date_trunc('month', order_date)::date AS month, category, SUM(subtotal) AS revenue
        FROM f WHERE is_revenue GROUP BY 1, 2 ORDER BY 1, 2
    """, f.params())


# ---------------------------------------------------------------- products
def top_products(f: Filters, by: str = "units", n: int = 10) -> pd.DataFrame:
    order_col = {"units": "units", "revenue": "revenue"}[by]   # whitelist
    return run_query(ITEMS_CTE + f"""
        SELECT product_name, category, SUM(quantity) AS units, SUM(subtotal) AS revenue,
               SUM(subtotal) - SUM(item_cost) AS gross_profit
        FROM f WHERE is_revenue GROUP BY 1, 2 ORDER BY {order_col} DESC, product_name LIMIT :n
    """, {**f.params(), "n": n})


def product_stock(f: Filters) -> pd.DataFrame:
    """Stock is a current snapshot (not date-filtered). Units sold uses the date filter."""
    return run_query(f"""
        SELECT p.product_id, p.product_name, p.category, p.unit_price, p.cost_price, p.stock_quantity,
               COALESCE(s.units_sold, 0) AS units_sold,
               (p.stock_quantity < :low) AS low_stock
        FROM products p
        LEFT JOIN (
            SELECT oi.product_id, SUM(oi.quantity) AS units_sold
            FROM order_items oi JOIN orders o ON o.order_id = oi.order_id
            WHERE o.order_status IN {REV} AND o.order_date BETWEEN :start AND :end
            GROUP BY 1) s ON s.product_id = p.product_id
        WHERE (CAST(:cats AS text[]) IS NULL OR p.category = ANY(CAST(:cats AS text[])))
        ORDER BY p.stock_quantity
    """, {**f.params(), "low": config.LOW_STOCK_THRESHOLD})


# ---------------------------------------------------------------- customers
def top_customers(f: Filters, n: int = 10) -> pd.DataFrame:
    return run_query(ITEMS_CTE + """
        SELECT customer_id, customer_name, city, SUM(subtotal) AS total_spent,
               COUNT(DISTINCT order_id) AS orders
        FROM f WHERE is_revenue GROUP BY 1, 2, 3 ORDER BY total_spent DESC LIMIT :n
    """, {**f.params(), "n": n})


def customers_by_city(f: Filters) -> pd.DataFrame:
    return run_query("""
        SELECT city, state, COUNT(*) AS customers FROM customers c
        WHERE (CAST(:cities AS text[]) IS NULL OR c.city = ANY(CAST(:cities AS text[])))
        GROUP BY 1, 2 ORDER BY customers DESC
    """, f.params())


def registrations_by_month(f: Filters) -> pd.DataFrame:
    return run_query("""
        SELECT date_trunc('month', registration_date)::date AS month, COUNT(*) AS new_customers
        FROM customers c
        WHERE (CAST(:cities AS text[]) IS NULL OR c.city = ANY(CAST(:cities AS text[])))
        GROUP BY 1 ORDER BY 1
    """, f.params())


def repeat_customers(f: Filters) -> pd.DataFrame:
    """Buckets customers by number of revenue orders in the period."""
    return run_query(ITEMS_CTE + """
        , per_customer AS (
            SELECT customer_id, COUNT(DISTINCT order_id) AS n_orders, SUM(subtotal) AS spent
            FROM f WHERE is_revenue GROUP BY 1)
        SELECT CASE WHEN n_orders = 1 THEN '1 order' WHEN n_orders = 2 THEN '2 orders'
                    WHEN n_orders = 3 THEN '3 orders' ELSE '4+ orders' END AS bucket,
               COUNT(*) AS customers, SUM(spent) AS revenue
        FROM per_customer GROUP BY 1 ORDER BY 1
    """, f.params())


def customer_behaviour(f: Filters) -> dict:
    df = run_query(ITEMS_CTE + """
        , per_order AS (
            SELECT order_id, customer_id, SUM(quantity) AS units, COUNT(*) AS lines
            FROM f WHERE is_revenue GROUP BY 1, 2)
        SELECT COUNT(DISTINCT customer_id)                          AS buyers,
               COUNT(*)::numeric / NULLIF(COUNT(DISTINCT customer_id),0) AS orders_per_customer,
               AVG(units)                                           AS units_per_order,
               AVG(lines)                                           AS products_per_order
        FROM per_order
    """, f.params()).iloc[0]
    return {k: float(v or 0) for k, v in df.items()}


# ---------------------------------------------------------------- orders
def orders_by_status(f: Filters) -> pd.DataFrame:
    return run_query(f"""
        SELECT o.order_status, COUNT(*) AS orders, SUM(o.total_amount) AS order_value
        FROM orders o JOIN customers c ON c.customer_id = o.customer_id
        WHERE {ORDER_WHERE} GROUP BY 1 ORDER BY orders DESC
    """, f.params())


def monthly_orders_by_status(f: Filters) -> pd.DataFrame:
    return run_query(f"""
        SELECT date_trunc('month', o.order_date)::date AS month, o.order_status, COUNT(*) AS orders
        FROM orders o JOIN customers c ON c.customer_id = o.customer_id
        WHERE {ORDER_WHERE} GROUP BY 1, 2 ORDER BY 1, 2
    """, f.params())


def monthly_aov(f: Filters) -> pd.DataFrame:
    return run_query(f"""
        SELECT date_trunc('month', o.order_date)::date AS month,
               ROUND(AVG(o.total_amount), 2) AS avg_order_value, COUNT(*) AS orders
        FROM orders o JOIN customers c ON c.customer_id = o.customer_id
        WHERE o.order_status IN {REV} AND {ORDER_WHERE} GROUP BY 1 ORDER BY 1
    """, f.params())


def order_size_distribution(f: Filters) -> pd.DataFrame:
    return run_query(f"""
        SELECT n_items || CASE WHEN n_items = 1 THEN ' product' ELSE ' products' END AS order_size,
               COUNT(*) AS orders, ROUND(AVG(total_amount), 2) AS avg_value
        FROM (SELECT o.order_id, o.total_amount, COUNT(oi.order_item_id) AS n_items
              FROM orders o JOIN customers c ON c.customer_id = o.customer_id
              JOIN order_items oi ON oi.order_id = o.order_id
              WHERE {ORDER_WHERE} GROUP BY 1, 2) t
        GROUP BY n_items ORDER BY n_items
    """, f.params())


# ---------------------------------------------------------------- payments
def payments_by_method(f: Filters) -> pd.DataFrame:
    return run_query(f"""
        SELECT pay.payment_method,
               COUNT(*)                                                     AS attempts,
               COUNT(*) FILTER (WHERE pay.payment_status = 'success')      AS successful,
               COUNT(*) FILTER (WHERE pay.payment_status = 'failed')       AS failed,
               COALESCE(SUM(pay.amount) FILTER (WHERE pay.payment_status = 'success'), 0) AS success_amount,
               ROUND(100.0 * COUNT(*) FILTER (WHERE pay.payment_status = 'failed') / COUNT(*), 1) AS failure_rate_pct
        FROM payments pay JOIN orders o ON o.order_id = pay.order_id
        JOIN customers c ON c.customer_id = o.customer_id
        WHERE {ORDER_WHERE} GROUP BY 1 ORDER BY attempts DESC
    """, f.params())


def payments_by_status(f: Filters) -> pd.DataFrame:
    return run_query(f"""
        SELECT pay.payment_status, COUNT(*) AS payments, SUM(pay.amount) AS amount
        FROM payments pay JOIN orders o ON o.order_id = pay.order_id
        JOIN customers c ON c.customer_id = o.customer_id
        WHERE {ORDER_WHERE} GROUP BY 1 ORDER BY payments DESC
    """, f.params())
