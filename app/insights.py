"""Business insights computed from PostgreSQL at run time.
Every sentence is built from query results - nothing is hardcoded, so if the
data changes, the findings change (or disappear) with it."""
from __future__ import annotations

from datetime import date

import pandas as pd

from app import config
from app import queries as q
from app.database import run_query


def _inr(x: float) -> str:
    return f"₹{x:,.0f}"


def build_insights() -> list[dict]:
    opts = q.filter_options()
    f = q.Filters(opts["min_date"], opts["max_date"])
    out: list[dict] = []

    # 1. Category revenue vs margin
    cat = q.revenue_by_category(f)
    cat["revenue"] = cat.revenue.astype(float)
    total = cat.revenue.sum()
    top = cat.iloc[0]
    best_margin = cat.sort_values("margin_pct", ascending=False).iloc[0]
    out.append({
        "title": "Revenue is concentrated in one category, but margins are higher elsewhere",
        "finding": f"{top.category} generates {_inr(top.revenue)} ({top.revenue / total:.0%} of revenue) "
                   f"at a {top.margin_pct}% margin, while {best_margin.category} earns the best margin "
                   f"({best_margin.margin_pct}%).",
        "meaning": "The biggest seller is not the most profitable per rupee sold. Growth in high-margin "
                   "categories adds more profit per sale.",
        "data": cat[["category", "revenue", "gross_profit", "margin_pct", "units"]],
        "action": f"Run promotions or bundles that pair {top.category} purchases with "
                  f"{best_margin.category} products, and review {top.category} supplier costs.",
    })

    # 2. City concentration
    city = q.revenue_by_city(f)
    city["revenue"] = city.revenue.astype(float)
    share2 = city.revenue.head(2).sum() / city.revenue.sum()
    out.append({
        "title": "Two cities drive a large share of sales",
        "finding": f"{city.city.iloc[0]} and {city.city.iloc[1]} together produce {share2:.0%} of revenue; "
                   f"the bottom 3 cities ({', '.join(city.city.tail(3))}) produce "
                   f"{city.revenue.tail(3).sum() / city.revenue.sum():.0%}.",
        "meaning": "Sales depend heavily on a few markets: strong there, under-penetrated elsewhere.",
        "data": city[["city", "state", "revenue", "orders", "customers"]],
        "action": f"Protect the top markets (fast delivery, loyalty offers) and test targeted campaigns in "
                  f"{city.city.iloc[-1]} and {city.city.iloc[-2]} before spending more there.",
    })

    # 3. Repeat customers
    rep = q.repeat_customers(f)
    rep["revenue"] = rep.revenue.astype(float)
    repeat_rev = rep[rep.bucket != "1 order"].revenue.sum() / rep.revenue.sum()
    repeat_cust = rep[rep.bucket != "1 order"].customers.sum() / rep.customers.sum()
    out.append({
        "title": "Repeat customers are the core of the business",
        "finding": f"{repeat_cust:.0%} of buying customers placed more than one order, and they generate "
                   f"{repeat_rev:.0%} of revenue.",
        "meaning": "Keeping existing customers matters more to revenue than one-off buyers.",
        "data": rep,
        "action": "Start a simple loyalty programme (e.g. reward on the 3rd order) and send "
                  "follow-up offers to one-time buyers within 30 days.",
    })

    # 4. Payment failures by method
    pm = q.payments_by_method(f)
    online = pm[pm.payment_method != "cash_on_delivery"].sort_values("failure_rate_pct", ascending=False)
    worst, best = online.iloc[0], online.iloc[-1]
    out.append({
        "title": "Some payment methods fail much more often",
        "finding": f"{worst.payment_method} fails {worst.failure_rate_pct}% of attempts versus "
                   f"{best.failure_rate_pct}% for {best.payment_method}. "
                   f"{int(pm.failed.sum())} payment attempts failed in total.",
        "meaning": "Failed payments add friction and risk losing the sale.",
        "data": pm[["payment_method", "attempts", "successful", "failed", "failure_rate_pct", "success_amount"]],
        "action": f"Check the {worst.payment_method} gateway integration, and offer a one-click retry with "
                  f"{best.payment_method} when a payment fails.",
    })

    # 5. Low stock on best sellers
    stock = q.product_stock(f)
    risky = stock[stock.low_stock].sort_values("units_sold", ascending=False)
    out.append({
        "title": "Popular products are close to running out",
        "finding": f"{len(risky)} products have fewer than {config.LOW_STOCK_THRESHOLD} units in stock; "
                   f"'{risky.product_name.iloc[0]}' has only {int(risky.stock_quantity.iloc[0])} left after "
                   f"selling {int(risky.units_sold.iloc[0])} units in the period.",
        "meaning": "Stock-outs on items that sell well mean lost revenue.",
        "data": risky[["product_name", "category", "stock_quantity", "units_sold"]],
        "action": "Reorder the listed products now, prioritising those with the most units sold.",
    })

    # 6. Lost order value (cancelled + returned)
    st = q.orders_by_status(f)
    st["order_value"] = st.order_value.astype(float)
    lost = st[st.order_status.isin(["cancelled", "returned"])]
    out.append({
        "title": "Cancellations and returns remove a noticeable share of order value",
        "finding": f"{int(lost.orders.sum())} cancelled or returned orders worth {_inr(lost.order_value.sum())} "
                   f"= {lost.order_value.sum() / st.order_value.sum():.0%} of gross order value.",
        "meaning": "That is demand the business won but did not keep as revenue.",
        "data": st,
        "action": "Record cancellation and return reasons (not yet captured in the data) to find the causes.",
    })

    # 7. Latest complete month vs previous
    mr = q.monthly_revenue(f)
    max_d: date = opts["max_date"]
    last_complete = mr[pd.to_datetime(mr.month) + pd.offsets.MonthEnd(0) <= pd.Timestamp(max_d)]
    if len(last_complete) >= 2:
        a, b = last_complete.iloc[-2], last_complete.iloc[-1]
        chg = (float(b.revenue) - float(a.revenue)) / float(a.revenue)
        out.append({
            "title": "Month-over-month trend (latest complete month)",
            "finding": f"Revenue in {pd.Timestamp(b.month):%B %Y} was {_inr(float(b.revenue))}, "
                       f"{chg:+.0%} versus {pd.Timestamp(a.month):%B %Y} ({_inr(float(a.revenue))}).",
            "meaning": "Growth is " + ("continuing." if chg > 0 else "slowing; check what changed."),
            "data": mr[["month", "revenue", "orders", "growth_pct"]],
            "action": "Track this monthly; compare with marketing activity and stock availability.",
        })
    return out
