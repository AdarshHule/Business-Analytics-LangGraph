"""Streamlit entry point.  Run:  streamlit run app/main.py
Uses st.navigation (explicit page registry) instead of Streamlit's automatic pages/ folder."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # so `import app...` works

import streamlit as st  # noqa: E402

from app import config, database  # noqa: E402

st.set_page_config(page_title="Business Intelligence Platform", page_icon="📊", layout="wide")
st.markdown("""<style>
[data-testid="stMetric"] {background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;padding:14px 16px;}
[data-testid="stMetricValue"] {font-size:1.6rem;}
.block-container {padding-top:2rem;}
</style>""", unsafe_allow_html=True)

ok, msg = database.ping()
if not ok:
    st.error(f"**Cannot connect to PostgreSQL** at `{config.DB_HOST}:{config.DB_PORT}`.\n\n`{msg}`\n\n"
             "Check that the database container is running: `docker compose ps`")
    st.stop()

from app.components.sidebar import filters  # noqa: E402
from app.views import (ai_business_analyst, business_insights, customer_analytics,  # noqa: E402
                       database_explorer, executive_overview, langgraph_architecture,
                       order_analytics, payment_analytics, product_analytics, sales_analytics)


def page(module, title, icon, uses_filters=True):
    def _run():
        module.render(filters() if uses_filters else None)
    _run.__name__ = module.__name__.split(".")[-1]
    return st.Page(_run, title=title, icon=icon, url_path=_run.__name__)


nav = st.navigation({
    "Dashboard": [
        page(executive_overview, "Executive Overview", "🏠"),
        page(sales_analytics, "Sales Analytics", "📈"),
        page(product_analytics, "Product Analytics", "📦"),
        page(customer_analytics, "Customer Analytics", "👥"),
        page(order_analytics, "Order Analytics", "🧾"),
        page(payment_analytics, "Payment Analytics", "💳"),
        page(business_insights, "Business Insights", "💡", uses_filters=False),
    ],
    "Data & AI": [
        page(database_explorer, "Database Explorer", "🗄️", uses_filters=False),
        page(ai_business_analyst, "AI Business Analyst", "🤖", uses_filters=False),
        page(langgraph_architecture, "LangGraph Architecture", "🔀", uses_filters=False),
    ],
})
with st.sidebar:
    st.markdown("## 📊 BI Platform")
    st.caption(f"PostgreSQL ✅ · AI {'✅ ' + config.LLM_PROVIDER if config.llm_configured() else '⚪ not configured'}")
nav.run()
