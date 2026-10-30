import streamlit as st

from app import queries as q
from app.components import charts
from app.components.kpi_cards import inr, kpi_row


def render(f: q.Filters) -> None:
    st.title("Customer Analytics")
    b = q.customer_behaviour(f)
    rep = q.repeat_customers(f)
    repeat = int(rep[rep.bucket != "1 order"].customers.sum()) if not rep.empty else 0
    kpi_row([
        ("Buying customers", f"{int(b['buyers'])}", "Customers with at least one revenue order"),
        ("Repeat customers", f"{repeat}", "More than one revenue order in the period"),
        ("Orders per customer", f"{b['orders_per_customer']:.2f}", None),
        ("Units per order", f"{b['units_per_order']:.2f}", None),
    ])
    c1, c2 = st.columns(2)
    with c1:
        top = q.top_customers(f, 10)
        charts.bar(top, "total_spent", "customer_name", "Top 10 customers by spending", horizontal=True, height=420)
    with c2:
        charts.bar(q.customers_by_city(f), "city", "customers", "Customer distribution by city (registered)", money=False,
                   height=420)
    c3, c4 = st.columns(2)
    with c3:
        charts.line(q.registrations_by_month(f), "month", "new_customers", "Customer registrations over time", money=False)
    with c4:
        charts.bar(rep, "bucket", "revenue", "Repeat customer analysis: revenue by order count")
    st.markdown("**Customers by number of orders**")
    st.dataframe(rep, width="stretch", hide_index=True)
    st.caption(f"Average products per order: {b['products_per_order']:.2f}. "
               f"Top customer spent {inr(float(top.total_spent.iloc[0])) if not top.empty else '-'}.")
