import streamlit as st

from app import config
from app import queries as q
from app.components import charts


def render(f: q.Filters) -> None:
    st.title("Product Analytics")
    c1, c2 = st.columns(2)
    with c1:
        charts.bar(q.top_products(f, "units", 10), "units", "product_name", "Top 10 products by units sold",
                   horizontal=True, money=False, height=420)
    with c2:
        charts.bar(q.top_products(f, "revenue", 10), "revenue", "product_name", "Top 10 products by revenue",
                   horizontal=True, height=420)
    cat = q.revenue_by_category(f)
    c3, c4 = st.columns(2)
    with c3:
        long = cat.melt(id_vars="category", value_vars=["revenue", "gross_profit"], var_name="metric", value_name="amount")
        charts.bar(long, "category", "amount", "Category performance: revenue vs gross profit", color="metric")
    with c4:
        charts.bar(cat, "category", "margin_pct", "Profit margin by category (%)", money=False)

    st.subheader("Stock availability")
    stock = q.product_stock(f)
    stock["status"] = stock.low_stock.map({True: "Low stock", False: "OK"})
    charts.bar(stock, "stock_quantity", "product_name", f"Current stock (low < {config.LOW_STOCK_THRESHOLD} units)",
               horizontal=True, money=False, color="status", height=620,
               color_map={"Low stock": "#EF4444", "OK": "#14B8A6"})
    low = stock[stock.low_stock]
    st.markdown(f"**{len(low)} low-stock products** (sorted by units sold in the selected period):")
    st.dataframe(low.sort_values("units_sold", ascending=False)[
        ["product_name", "category", "stock_quantity", "units_sold", "unit_price"]],
        width="stretch", hide_index=True)
