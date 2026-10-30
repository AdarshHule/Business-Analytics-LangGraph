"""LangGraph NODES. Each node = a plain Python function: (state) -> partial state update.

The LLM is injected through an `LLMClient`, so tests can swap in a fake LLM and
check the graph logic without an API key (and without spending money).
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime
from decimal import Decimal
from functools import wraps
from typing import Any, Callable, Literal, Optional, Protocol, Type, TypeVar

from pydantic import BaseModel, Field
from sqlalchemy import text

from app import config
from app.ai import prompts
from app.ai.sql_validator import ALLOWED_TABLES, validate_sql
from app.ai.state import AnalystState

T = TypeVar("T", bound=BaseModel)


# ------------------------------------------------------------------ LLM output schemas
class Understanding(BaseModel):
    objective: str = Field(description="Precise analytical objective")
    needs_clarification: bool = False
    clarification_question: Optional[str] = None


class TableSelection(BaseModel):
    tables: list[str] = Field(description="Table names needed")
    join_path: str = Field(description="How the tables join, e.g. orders.customer_id = customers.customer_id")


class GeneratedSQL(BaseModel):
    sql: str = Field(description="A single PostgreSQL SELECT statement, no semicolon")
    explanation: str = Field(description="One sentence: what the query computes")


class ChartSpec(BaseModel):
    type: Literal["metric", "bar", "line", "pie", "table"] = "table"
    x: Optional[str] = None
    y: Optional[str] = None
    title: str = ""


class Analysis(BaseModel):
    answer: str
    key_findings: list[str]
    business_interpretation: str
    chart: ChartSpec


# ------------------------------------------------------------------ LLM client
class LLMClient(Protocol):
    def structured(self, schema: Type[T], system: str, user: str) -> T: ...


class LangChainLLM:
    """Provider-independent wrapper: Anthropic or OpenAI chosen by environment variable."""

    def __init__(self) -> None:
        if config.LLM_PROVIDER == "anthropic":
            from langchain_anthropic import ChatAnthropic
            # Current Claude models reject a custom temperature and forced tool calling,
            # so use the default temperature and native JSON-schema structured output.
            self.llm = ChatAnthropic(model=config.LLM_MODEL or "claude-sonnet-5-5",
                                     api_key=config.ANTHROPIC_API_KEY, max_tokens=2000, timeout=60)
            self.structured_kwargs = {"method": "json_schema"}
        elif config.LLM_PROVIDER == "openai":
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(model=config.LLM_MODEL or "gpt-4o-mini",
                                  api_key=config.OPENAI_API_KEY, temperature=0, timeout=60)
            self.structured_kwargs = {}
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER '{config.LLM_PROVIDER}'")

    def structured(self, schema: Type[T], system: str, user: str) -> T:
        return self.llm.with_structured_output(schema, **self.structured_kwargs).invoke(
            [("system", system), ("human", user)])


# ------------------------------------------------------------------ helpers
def traced(name: str) -> Callable:
    """Decorator: records node name, timing and a short status in state['trace']."""
    def deco(fn: Callable[[AnalystState], dict]) -> Callable[[AnalystState], dict]:
        @wraps(fn)
        def wrapper(state: AnalystState) -> dict:
            t0 = time.perf_counter()
            try:
                update = fn(state)
                status = update.pop("_status", "ok")
            except Exception as exc:  # noqa: BLE001 - never crash the graph
                # failed_node makes the routers stop the run instead of looping.
                update = {"error_message": f"{name} failed: {exc}", "failed_node": name}
                status = "error"
            update["trace"] = [{"node": name, "status": status,
                                "ms": round((time.perf_counter() - t0) * 1000)}]
            return update
        return wrapper
    return deco


def _json_safe(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def _schema_for(tables: list[str], full_schema: str) -> str:
    """Keep only the schema blocks of the chosen tables."""
    out, keep = [], False
    for line in full_schema.splitlines():
        if line.startswith("TABLE "):
            keep = line.split("(")[0].split()[1] in tables
        if keep:
            out.append(line)
    return "\n".join(out)


# ------------------------------------------------------------------ node factory
def make_nodes(llm: LLMClient, engine, schema_text: str) -> dict[str, Callable]:
    """Builds the 7 nodes as closures over the LLM, DB engine and live schema."""

    @traced("understand_question")
    def understand_question(state: AnalystState) -> dict:
        u = llm.structured(Understanding, prompts.UNDERSTAND_SYSTEM, state["user_question"])
        return {"objective": u.objective, "needs_clarification": u.needs_clarification,
                "clarification_question": u.clarification_question, "retry_count": 0,
                "error_message": None,
                "_status": "needs clarification" if u.needs_clarification else "ok"}

    @traced("identify_tables")
    def identify_tables(state: AnalystState) -> dict:
        sel = llm.structured(TableSelection, prompts.IDENTIFY_SYSTEM.format(schema=schema_text),
                             f"Question: {state['user_question']}\nObjective: {state['objective']}")
        tables = [t.lower() for t in sel.tables if t.lower() in ALLOWED_TABLES] or sorted(ALLOWED_TABLES)
        return {"identified_tables": tables,
                "relevant_schema": _schema_for(tables, schema_text) + f"\nJOIN PATH: {sel.join_path}"}

    @traced("generate_sql")
    def generate_sql(state: AnalystState) -> dict:
        user = f"Question: {state['user_question']}\nObjective: {state['objective']}"
        if state.get("error_message") and state.get("generated_sql"):
            # Self-correction: show the LLM its previous SQL and the exact error.
            user += (f"\n\nYour previous SQL failed. Fix it.\nPrevious SQL:\n{state['generated_sql']}"
                     f"\nError: {state['error_message']}")
        g = llm.structured(GeneratedSQL, prompts.GENERATE_SYSTEM.format(
            tables=", ".join(state["identified_tables"]), schema=state["relevant_schema"]), user)
        return {"generated_sql": g.sql.strip().rstrip(";"), "sql_explanation": g.explanation,
                "_status": f"attempt {state.get('retry_count', 0) + 1}"}

    @traced("validate_sql")
    def validate(state: AnalystState) -> dict:
        r = validate_sql(state["generated_sql"], max_rows=config.AI_MAX_ROWS)
        if r.is_valid:
            return {"validation_status": "valid", "validated_sql": r.sql, "error_message": None}
        return {"validation_status": "invalid", "error_message": "Rejected by validator: " + "; ".join(r.errors),
                "retry_count": state.get("retry_count", 0) + 1, "_status": "rejected"}

    @traced("execute_sql")
    def execute_sql(state: AnalystState) -> dict:
        try:
            with engine.connect() as conn:
                conn.execute(text("SET TRANSACTION READ ONLY"))   # layer 3
                res = conn.execute(text(state["validated_sql"]))
                cols = list(res.keys())
                rows = [{c: _json_safe(v) for c, v in zip(cols, row)} for row in res.fetchall()]
                conn.rollback()
        except Exception as exc:  # noqa: BLE001
            msg = str(getattr(exc, "orig", exc)).splitlines()[0]
            return {"error_message": f"Database error: {msg}", "query_results": [], "row_count": 0,
                    "retry_count": state.get("retry_count", 0) + 1, "_status": "db error"}
        return {"query_results": rows, "result_columns": cols, "row_count": len(rows),
                "error_message": None, "_status": f"{len(rows)} rows"}

    @traced("analyze_results")
    def analyze_results(state: AnalystState) -> dict:
        rows = state["query_results"][:50]
        user = (f"Question: {state['user_question']}\nSQL executed:\n{state['validated_sql']}\n"
                f"Columns: {state['result_columns']}\nRows ({len(rows)} of {state['row_count']} shown):\n"
                f"{json.dumps(rows, default=str)}")
        a = llm.structured(Analysis, prompts.ANALYZE_SYSTEM, user)
        chart = a.chart.model_dump()
        cols = state["result_columns"]
        if chart["type"] != "table" and (chart.get("x") not in cols and chart["type"] != "metric"
                                         or chart.get("y") not in cols):
            chart = _fallback_chart(state)            # LLM picked a non-existent column
        return {"analysis": a.model_dump(exclude={"chart"}), "chart_recommendation": chart}

    @traced("generate_response")
    def generate_response(state: AnalystState) -> dict:
        if state.get("needs_clarification"):
            msg = state.get("clarification_question") or "This question can't be answered from the store's data."
            return {"final_response": f"**I need clarification:** {msg}", "_status": "clarification"}
        if state.get("error_message"):
            return {"final_response": ("**I could not answer this question safely.**\n\n"
                                       f"Last error: `{state['error_message']}`\n\n"
                                       "Try rephrasing it, e.g. naming the metric and time period."),
                    "_status": "failed"}
        if state.get("row_count", 0) == 0:
            return {"final_response": ("**No matching data.** The query ran successfully but returned no rows, "
                                       "so there is nothing to report for this question (I will not guess)."),
                    "chart_recommendation": {"type": "table"}, "_status": "empty"}
        a = state["analysis"]
        findings = "\n".join(f"- {f}" for f in a.get("key_findings", []))
        return {"final_response": (f"{a['answer']}\n\n**Key findings**\n{findings}\n\n"
                                   f"**Business interpretation:** {a['business_interpretation']}")}

    return {"understand_question": understand_question, "identify_tables": identify_tables,
            "generate_sql": generate_sql, "validate_sql": validate, "execute_sql": execute_sql,
            "analyze_results": analyze_results, "generate_response": generate_response}


def _fallback_chart(state: AnalystState) -> dict:
    rows, cols = state["query_results"], state["result_columns"]
    if not rows:
        return {"type": "table"}
    numeric = [c for c in cols if isinstance(rows[0].get(c), (int, float))]
    other = [c for c in cols if c not in numeric]
    if len(rows) == 1 and numeric:
        return {"type": "metric", "y": numeric[0], "title": numeric[0]}
    if numeric and other:
        x = other[0]
        kind = "line" if any(k in x.lower() for k in ("month", "date", "day", "week")) else "bar"
        return {"type": kind, "x": x, "y": numeric[0], "title": f"{numeric[0]} by {x}"}
    return {"type": "table"}
