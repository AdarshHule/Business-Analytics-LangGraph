import streamlit as st

from app import queries as q
from app.components import charts
from app.components.kpi_cards import inr, kpi_row


def render(f: q.Filters) -> None:
    st.title("Payment Analytics")
    pm = q.payments_by_method(f)
    ps = q.payments_by_status(f)
    attempts = int(pm.attempts.sum())
    failed = int(pm.failed.sum())
    kpi_row([("Payment attempts", f"{attempts}", None),
             ("Successful amount", inr(float(pm.success_amount.sum())), "Sum of 'success' payments"),
             ("Failed attempts", f"{failed}", None),
             ("Failure rate", f"{failed / attempts:.1%}" if attempts else "-", "Failed ÷ all attempts")])
    c1, c2 = st.columns(2)
    with c1:
        charts.donut(pm, "payment_method", "attempts", "Payment methods distribution (attempts)")
    with c2:
        long = pm.melt(id_vars="payment_method", value_vars=["successful", "failed"], var_name="result", value_name="count")
        charts.bar(long, "payment_method", "count", "Successful vs failed payments", money=False, color="result",
                   color_map={"successful": "#14B8A6", "failed": "#EF4444"})
    c3, c4 = st.columns(2)
    with c3:
        charts.bar(pm, "payment_method", "success_amount", "Successful payment amount by method")
    with c4:
        charts.donut(ps, "payment_status", "payments", "Payment status breakdown", color_map=charts.STATUS_COLORS)
    st.dataframe(pm, width="stretch", hide_index=True)
