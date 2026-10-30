import pandas as pd
import streamlit as st

from app import config
from app.components import charts

EXAMPLES = [
    "What is my total revenue this month?",
    "Which are my top five products by revenue?",
    "Which city generates the highest revenue?",
    "Which customers have purchased more than once?",
    "What is the monthly sales trend?",
    "Which payment method is most popular?",
    "Which products have low stock?",
    "Compare this month's sales with the previous month.",
    "Which product category generates the highest profit?",
]


@st.cache_resource
def _graph():
    from app.ai.graph import build_graph
    return build_graph()


def render(_f=None) -> None:
    st.title("AI Business Analyst")
    st.caption("Ask a business question in plain English. A LangGraph workflow turns it into a safe, read-only SQL "
               "query, runs it on PostgreSQL and explains the actual results.")
    if not config.llm_configured():
        st.warning(f"""**The AI Business Analyst is not configured.**

It needs an LLM provider API key. Set these in your `.env` file and restart the app with `docker compose up -d`:
`LLM_PROVIDER=anthropic` with `ANTHROPIC_API_KEY=...`, or `LLM_PROVIDER=openai` with `OPENAI_API_KEY=...`.

Current provider setting: `{config.LLM_PROVIDER}` · key found: **no**. The dashboards and Database Explorer
work without it.""")
        return

    st.markdown("**Example questions**")
    cols = st.columns(3)
    for i, ex in enumerate(EXAMPLES):
        if cols[i % 3].button(ex, key=f"ex{i}", width="stretch"):
            st.session_state["q"] = ex
    question = st.text_input("Your question", key="q", placeholder="e.g. Which city generates the highest revenue?")
    if not st.button("Ask", type="primary") or not question.strip():
        return

    graph = _graph()
    state: dict = {}
    with st.status("Running LangGraph workflow…", expanded=True) as status:
        # stream_mode="updates" yields after EACH node, so the user sees progress live.
        for event in graph.stream({"user_question": question.strip(), "trace": []},
                                   {"recursion_limit": 25}, stream_mode="updates"):
            for node, update in event.items():
                state.update({k: v for k, v in (update or {}).items() if k != "trace"})
                t = (update or {}).get("trace", [{}])[0]
                icon = "❌" if t.get("status") in ("error", "rejected", "db error", "failed") else "✅"
                st.write(f"{icon} **{node}** · {t.get('status', '')} · {t.get('ms', 0)} ms")
                state.setdefault("trace", []).extend(update.get("trace", []) if update else [])
        failed = bool(state.get("error_message"))
        status.update(label="Workflow finished" + (" with errors" if failed else ""),
                      state="error" if failed else "complete", expanded=False)

    st.subheader("Answer")
    st.markdown(state.get("final_response", "No response."))

    c1, c2 = st.columns([3, 2])
    with c1:
        if state.get("generated_sql"):
            st.markdown("**SQL executed**" if state.get("validation_status") == "valid" else "**SQL generated**")
            st.code(state.get("validated_sql") or state.get("generated_sql"), language="sql")
    with c2:
        st.markdown("**Workflow details**")
        st.markdown(f"- Objective: {state.get('objective', '-')}")
        st.markdown(f"- Tables: `{', '.join(state.get('identified_tables', []))}`")
        v = state.get("validation_status", "-")
        st.markdown(f"- SQL validation: {'✅ valid (read-only SELECT)' if v == 'valid' else '❌ ' + str(v)}")
        st.markdown(f"- Rows returned: {state.get('row_count', 0)} · retries: {state.get('retry_count', 0)}")

    rows = state.get("query_results") or []
    if rows:
        df = pd.DataFrame(rows, columns=state.get("result_columns"))
        st.markdown("**Query results**")
        st.dataframe(df, width="stretch", hide_index=True)
        spec = state.get("chart_recommendation") or {}
        st.markdown(f"**Recommended visualization:** `{spec.get('type', 'table')}`")
        if not charts.auto_chart(df, spec):
            st.caption("A table is the best view for this result.")
