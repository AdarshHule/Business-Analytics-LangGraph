import streamlit as st

from app import queries as q
from app.components import charts
from app.components.kpi_cards import inr, kpi_row


def render(f: q.Filters) -> None:
    st.title("Order Analytics")
    st_df = q.orders_by_status(f)
    total = int(st_df.orders.sum())
    done = int(st_df[st_df.order_status == "delivered"].orders.sum())
    lost = int(st_df[st_df.order_status.isin(["cancelled", "returned"])].orders.sum())
    k = q.kpis(f)
    kpi_row([("Total orders", f"{total}", None), ("Delivered", f"{done / total:.0%}" if total else "-", None),
             ("Cancelled + returned", f"{lost / total:.0%}" if total else "-", None),
             ("Avg order value", inr(k["aov"]), "Revenue orders only")])
    c1, c2 = st.columns(2)
    with c1:
        charts.donut(st_df, "order_status", "orders", "Orders by status", color_map=charts.STATUS_COLORS)
    with c2:
        charts.bar(q.monthly_orders_by_status(f), "month", "orders", "Order volume trend by status", money=False,
                   color="order_status", color_map=charts.STATUS_COLORS)
    c3, c4 = st.columns(2)
    with c3:
        charts.line(q.monthly_aov(f), "month", "avg_order_value", "Average order value by month")
    with c4:
        charts.bar(q.order_size_distribution(f), "order_size", "orders", "Order performance: orders by basket size",
                   money=False)
    st.dataframe(st_df, width="stretch", hide_index=True)
    st.caption("Category filter on this page keeps orders that contain at least one product in the category.")
