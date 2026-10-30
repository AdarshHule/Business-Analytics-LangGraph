import streamlit as st

from app import queries as q
from app.components import charts


def render(f: q.Filters) -> None:
    st.title("Sales Analytics")
    mr = q.monthly_revenue(f)
    c1, c2 = st.columns(2)
    with c1:
        charts.bar(mr, "month", "revenue", "Monthly revenue")
    with c2:
        g = mr.dropna(subset=["growth_pct"])
        charts.bar(g, "month", "growth_pct", "Month-over-month revenue growth (%)", money=False)
    charts.line(q.daily_revenue(f), "day", "revenue", "Daily sales trend", height=320)
    c3, c4 = st.columns(2)
    with c3:
        charts.bar(q.revenue_by_category(f), "revenue", "category", "Revenue by product category", horizontal=True)
    with c4:
        charts.bar(q.revenue_by_city(f), "revenue", "city", "Revenue by city", horizontal=True)
    charts.line(q.monthly_revenue_by_category(f), "month", "revenue", "Sales performance over time by category",
                color="category")
    with st.expander("Monthly figures (table)"):
        st.dataframe(mr, width="stretch", hide_index=True)
    st.caption("The latest month may be partial; compare complete months for growth.")
