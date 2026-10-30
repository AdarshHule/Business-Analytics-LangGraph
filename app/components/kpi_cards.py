import streamlit as st


def inr(x: float) -> str:
    """Indian-style short format: ₹19.48 L, ₹1.2 Cr."""
    if abs(x) >= 1e7:
        return f"₹{x / 1e7:.2f} Cr"
    if abs(x) >= 1e5:
        return f"₹{x / 1e5:.2f} L"
    return f"₹{x:,.0f}"


def kpi_row(items: list[tuple[str, str, str | None]]) -> None:
    """items = [(label, value, help_text)]"""
    cols = st.columns(len(items))
    for col, (label, value, help_) in zip(cols, items):
        col.metric(label, value, help=help_)
