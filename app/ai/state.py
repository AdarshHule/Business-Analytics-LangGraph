"""LangGraph STATE: the shared, typed dictionary every node reads from and writes to.

Each node returns ONLY the keys it changed; LangGraph merges them into the state.
`trace` uses a *reducer* (operator.add): node outputs are APPENDED, not replaced,
so we keep a full execution history to show in the UI.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Optional, TypedDict


class AnalystState(TypedDict, total=False):
    # input
    user_question: str
    # understand_question
    objective: str
    needs_clarification: bool
    clarification_question: Optional[str]
    # identify_tables
    identified_tables: list[str]
    relevant_schema: str
    # generate_sql
    generated_sql: str
    sql_explanation: str
    # validate_sql
    validation_status: str            # "valid" | "invalid"
    validated_sql: str                # SQL after LIMIT enforcement
    # execute_sql
    query_results: list[dict[str, Any]]
    result_columns: list[str]
    row_count: int
    # analyze_results
    analysis: dict[str, Any]
    chart_recommendation: dict[str, Any]
    # generate_response
    final_response: str
    # error handling
    error_message: Optional[str]
    retry_count: int
    failed_node: Optional[str]        # set when a node raised; the run goes straight to generate_response
    trace: Annotated[list[dict[str, Any]], operator.add]
