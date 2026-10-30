import streamlit as st

from app.insights import build_insights


def render(_f=None) -> None:
    st.title("Business Insights")
    st.caption("Generated from live PostgreSQL queries over the full dataset (sidebar filters not applied). "
               "Each finding shows its supporting data.")
    for i, ins in enumerate(build_insights(), 1):
        with st.container(border=True):
            st.markdown(f"#### {i}. {ins['title']}")
            st.markdown(f"**Finding:** {ins['finding']}")
            st.markdown(f"**What it means:** {ins['meaning']}")
            st.markdown(f"**Suggested action:** {ins['action']}")
            with st.expander("Supporting data"):
                st.dataframe(ins["data"], width="stretch", hide_index=True)
