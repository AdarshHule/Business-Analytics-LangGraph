"""LangGraph WORKFLOW: wires the 7 nodes with edges and conditional edges.

    START -> understand_question --(clarify?)--> generate_response
                    | ok
             identify_tables -> generate_sql -> validate_sql
                                     ^             | invalid & retries left -> generate_sql
                                     |             | invalid & no retries   -> generate_response
                                     |             | valid
                                     |         execute_sql
                                     +-- db error & retries left
                                               | db error, no retries / 0 rows -> generate_response
                                               | rows
                                         analyze_results -> generate_response -> END
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app import config
from app.ai.nodes import LangChainLLM, LLMClient, make_nodes
from app.ai.state import AnalystState


# --------------------------------------------------------------- routing functions
def continue_or_stop(next_node: str):
    """Router for straight edges: stop if the previous node crashed (e.g. LLM API error)."""
    def route(state: AnalystState) -> str:
        return "generate_response" if state.get("failed_node") else next_node
    return route


def route_after_understand(state: AnalystState) -> str:
    if state.get("failed_node") or state.get("needs_clarification"):
        return "generate_response"
    return "identify_tables"


def route_after_validate(state: AnalystState) -> str:
    if state.get("failed_node"):
        return "generate_response"     # a crash is not fixable by regenerating SQL
    if state.get("validation_status") == "valid":
        return "execute_sql"
    if state.get("retry_count", 0) <= config.AI_MAX_RETRIES:
        return "generate_sql"          # retry with the validator's error message
    return "generate_response"


def route_after_execute(state: AnalystState) -> str:
    if state.get("failed_node"):
        return "generate_response"
    if state.get("error_message"):
        if state.get("retry_count", 0) <= config.AI_MAX_RETRIES:
            return "generate_sql"      # retry with the database's error message
        return "generate_response"
    if state.get("row_count", 0) == 0:
        return "generate_response"     # empty result: report it, never invent data
    return "analyze_results"


# --------------------------------------------------------------- graph builder
def _wire(nodes: dict):
    """Adds nodes + edges to a StateGraph and compiles it (single source of truth)."""
    g = StateGraph(AnalystState)
    for name, fn in nodes.items():
        g.add_node(name, fn)
    g.add_edge(START, "understand_question")
    g.add_conditional_edges("understand_question", route_after_understand,
                            ["identify_tables", "generate_response"])
    g.add_conditional_edges("identify_tables", continue_or_stop("generate_sql"),
                            ["generate_sql", "generate_response"])
    g.add_conditional_edges("generate_sql", continue_or_stop("validate_sql"),
                            ["validate_sql", "generate_response"])
    g.add_conditional_edges("validate_sql", route_after_validate,
                            ["execute_sql", "generate_sql", "generate_response"])
    g.add_conditional_edges("execute_sql", route_after_execute,
                            ["analyze_results", "generate_sql", "generate_response"])
    g.add_edge("analyze_results", "generate_response")   # on failure it goes there anyway
    g.add_edge("generate_response", END)
    return g.compile()


def build_graph(llm: LLMClient | None = None, engine=None, schema_text: str | None = None):
    from app import database
    engine = engine or database.get_engine()
    schema_text = schema_text if schema_text is not None else database.schema_text()
    return _wire(make_nodes(llm or LangChainLLM(), engine, schema_text))


def graph_mermaid() -> str:
    """Mermaid diagram generated FROM the compiled graph itself (not hand-drawn).
    Needs no LLM and no database: nodes are only drawn, never run."""
    return _wire(make_nodes(llm=None, engine=None, schema_text="")).get_graph().draw_mermaid()


def ask(question: str, graph=None) -> AnalystState:
    graph = graph or build_graph()
    return graph.invoke({"user_question": question, "trace": []}, {"recursion_limit": 25})
