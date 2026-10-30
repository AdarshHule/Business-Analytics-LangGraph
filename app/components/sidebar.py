"""Sidebar filters shared by all dashboard pages. Values come from the database."""
import streamlit as st

from app import queries as q


@st.cache_data(ttl=300)
def _options():
    return q.filter_options()


def filters() -> q.Filters:
    o = _options()
    with st.sidebar:
        st.markdown("### Filters")
        rng = st.date_input("Order date range", (o["min_date"], o["max_date"]),
                            min_value=o["min_date"], max_value=o["max_date"], format="DD/MM/YYYY")
        start, end = (rng if isinstance(rng, (tuple, list)) and len(rng) == 2 else (o["min_date"], o["max_date"]))
        cats = st.multiselect("Product category", o["categories"], placeholder="All categories")
        cities = st.multiselect("Customer city", o["cities"], placeholder="All cities")
        st.caption("Revenue = processing + shipped + delivered orders.")
    return q.Filters(start, end, tuple(cats) or None, tuple(cities) or None)
