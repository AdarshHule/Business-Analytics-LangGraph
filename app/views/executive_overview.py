import streamlit as st

from app import queries as q
from app.components import charts
from app.components.kpi_cards import inr, kpi_row


def render(f: q.Filters) -> None:
    st.title("Executive Overview")
    st.caption(f"{f.start:%d %b %Y} – {f.end:%d %b %Y} · all figures queried live from PostgreSQL")
    k = q.kpis(f)
    kpi_row([
        ("Total revenue", inr(k["revenue"]), "Processing + shipped + delivered orders"),
        ("Total orders", f"{k['total_orders']:,}", "All orders in the period, any status"),
        ("Customers", f"{k['customers']:,}", "Distinct customers who ordered"),
        ("Avg order value", inr(k["aov"]), "Revenue ÷ revenue orders"),
        ("Gross profit", inr(k["gross_profit"]), "Revenue − product cost"),
        ("Profit margin", f"{k['margin']:.1%}", "Gross profit ÷ revenue"),
    ])
    st.divider()
    mr = q.monthly_revenue(f)
    c1, c2 = st.columns([3, 2])
    with c1:
        long = mr.melt(id_vars="month", value_vars=["revenue", "gross_profit"], var_name="metric", value_name="amount")
        charts.line(long, "month", "amount", "Monthly revenue and gross profit", color="metric")
    with c2:
        charts.donut(q.revenue_by_category(f), "category", "revenue", "Revenue share by category")

    st.subheader("Business performance summary")
    paid = q.successful_payments_total(f)
    cat = q.revenue_by_category(f)
    city = q.revenue_by_city(f)
    if k["revenue"] and not cat.empty:
        best = mr.loc[mr.revenue.astype(float).idxmax()]
        st.markdown(f"""
- **Revenue** of **{inr(k['revenue'])}** from **{k['revenue_orders']}** completed orders, out of a gross
  order value of {inr(k['gross_order_value'])}. The difference is pending, cancelled and returned orders.
- **Successful payments** total {inr(paid)}. They {'match' if abs(paid - k['revenue']) < 1 else 'differ from'} revenue
  (reconciliation check).
- **Best month:** {best.month:%B %Y} ({inr(float(best.revenue))}).
- **Top category:** {cat.category.iloc[0]} ({inr(float(cat.revenue.iloc[0]))}); **top city:** {city.city.iloc[0]}.
""")
    else:
        st.info("No revenue in the selected filters.")
