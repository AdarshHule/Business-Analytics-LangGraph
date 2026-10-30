"""Plotly chart helpers so every chart shares one clean, consistent style."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

PALETTE = ["#2563EB", "#0EA5E9", "#14B8A6", "#F59E0B", "#8B5CF6", "#EF4444", "#64748B", "#EC4899"]
STATUS_COLORS = {"delivered": "#14B8A6", "shipped": "#0EA5E9", "processing": "#2563EB",
                 "pending": "#F59E0B", "cancelled": "#EF4444", "returned": "#8B5CF6",
                 "success": "#14B8A6", "failed": "#EF4444", "refunded": "#8B5CF6"}


def _style(fig: go.Figure, height: int = 360) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=50, b=10),
                      template="plotly_white", font=dict(size=13),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
                      title=dict(font=dict(size=16)), hoverlabel=dict(font_size=13))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#EEF2F7")
    return fig


def show(fig: go.Figure, height: int = 360) -> None:
    st.plotly_chart(_style(fig, height), width="stretch")


def _num(df: pd.DataFrame, cols) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def line(df, x, y, title, money=True, color=None, height=360):
    df = _num(df, [y])
    fig = px.line(df, x=x, y=y, title=title, markers=True, color=color,
                  color_discrete_sequence=PALETTE)
    if money:
        fig.update_yaxes(tickprefix="₹", tickformat=",.0f")
    show(fig, height)


def bar(df, x, y, title, money=True, horizontal=False, color=None, height=360, color_map=None):
    df = _num(df, [x] if horizontal else [y])
    if horizontal:
        fig = px.bar(df, x=x, y=y, orientation="h", title=title, color=color,
                     color_discrete_sequence=PALETTE, color_discrete_map=color_map)
        fig.update_yaxes(categoryorder="total ascending")
        if money:
            fig.update_xaxes(tickprefix="₹", tickformat=",.0f")
    else:
        fig = px.bar(df, x=x, y=y, title=title, color=color,
                     color_discrete_sequence=PALETTE, color_discrete_map=color_map)
        if money:
            fig.update_yaxes(tickprefix="₹", tickformat=",.0f")
    show(fig, height)


def donut(df, names, values, title, color_map=None, height=360):
    df = _num(df, [values])
    fig = px.pie(df, names=names, values=values, title=title, hole=0.55,
                 color=names, color_discrete_sequence=PALETTE, color_discrete_map=color_map)
    fig.update_traces(textposition="outside", textinfo="percent+label")
    fig.update_layout(showlegend=False)
    show(fig, height)


def auto_chart(df: pd.DataFrame, spec: dict) -> bool:
    """Draws the chart recommended by the AI workflow. Returns False if not drawable."""
    kind, x, y = spec.get("type", "table"), spec.get("x"), spec.get("y")
    title = spec.get("title") or ""
    if df.empty or kind == "table":
        return False
    if kind == "metric" and y in df.columns:
        st.metric(title or y, f"{pd.to_numeric(df[y].iloc[0]):,.2f}")
        return True
    if x not in df.columns or y not in df.columns:
        return False
    money = any(k in y.lower() for k in ("revenue", "amount", "spent", "profit", "value", "sales", "price"))
    if kind == "line":
        line(df, x, y, title, money=money)
    elif kind == "pie":
        donut(df, x, y, title)
    else:
        bar(df, x, y, title, money=money)
    return True
