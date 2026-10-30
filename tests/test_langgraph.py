"""LangGraph workflow tests.

Part A (always runs): a scripted FAKE LLM drives the real graph against the real
database, so we test routing, retries, validation, execution and empty results
deterministically without an API key.

Part B (runs only if an LLM key is configured): 5+ real natural-language questions.
"""
import pytest

from app import config
from app.ai.graph import build_graph, route_after_execute, route_after_validate
from app.ai.nodes import Analysis, ChartSpec, GeneratedSQL, TableSelection, Understanding


class FakeLLM:
    """Returns scripted outputs in order for each schema type."""

    def __init__(self, sqls, needs_clarification=False):
        self.sqls = list(sqls)
        self.clarify = needs_clarification
        self.calls = []

    def structured(self, schema, system, user):
        self.calls.append((schema.__name__, user))
        if schema is Understanding:
            return Understanding(objective="test objective", needs_clarification=self.clarify,
                                 clarification_question="Unrelated question" if self.clarify else None)
        if schema is TableSelection:
            return TableSelection(tables=["orders", "customers"], join_path="orders.customer_id = customers.customer_id")
        if schema is GeneratedSQL:
            return GeneratedSQL(sql=self.sqls.pop(0), explanation="test")
        if schema is Analysis:
            return Analysis(answer="Answer from rows", key_findings=["f1"], business_interpretation="bi",
                            chart=ChartSpec(type="bar", x="city", y="revenue"))
        raise AssertionError(schema)


def run(fake, q="test question"):
    return build_graph(llm=fake).invoke({"user_question": q, "trace": []})


def nodes_visited(state):
    return [t["node"] for t in state["trace"]]


CITY_SQL = ("SELECT c.city, SUM(o.total_amount) AS revenue FROM orders o JOIN customers c "
            "ON c.customer_id = o.customer_id WHERE o.order_status IN ('processing','shipped','delivered') "
            "GROUP BY c.city ORDER BY revenue DESC")


def test_happy_path(engine):
    s = run(FakeLLM([CITY_SQL]))
    assert nodes_visited(s) == ["understand_question", "identify_tables", "generate_sql", "validate_sql",
                                "execute_sql", "analyze_results", "generate_response"]
    assert s["validation_status"] == "valid"
    assert s["row_count"] == 10 and s["query_results"][0]["city"] == "Mumbai"
    assert s["identified_tables"] == ["orders", "customers"]
    assert s["chart_recommendation"]["x"] == "city"
    assert "Answer from rows" in s["final_response"]


def test_invalid_sql_is_retried_then_succeeds(engine):
    fake = FakeLLM(["DELETE FROM orders", CITY_SQL])
    s = run(fake)
    v = nodes_visited(s)
    assert v.count("generate_sql") == 2 and v.count("validate_sql") == 2
    assert s["row_count"] == 10
    retry_prompt = [u for name, u in fake.calls if name == "GeneratedSQL"][1]
    assert "Rejected by validator" in retry_prompt      # the LLM saw its own error


def test_database_error_is_retried(engine):
    s = run(FakeLLM(["SELECT no_such_column FROM orders", CITY_SQL]))
    assert nodes_visited(s).count("execute_sql") == 2
    assert s["row_count"] == 10 and s["error_message"] is None


def test_retries_are_limited(engine):
    s = run(FakeLLM(["DROP TABLE orders"] * 10))
    assert nodes_visited(s).count("generate_sql") == config.AI_MAX_RETRIES + 1
    assert nodes_visited(s)[-1] == "generate_response"
    assert "could not answer" in s["final_response"]
    assert "execute_sql" not in nodes_visited(s)      # unsafe SQL never reached the DB


def test_empty_result_is_reported_not_invented(engine):
    s = run(FakeLLM(["SELECT order_id FROM orders WHERE order_date > '2099-01-01'"]))
    assert s["row_count"] == 0
    assert "analyze_results" not in nodes_visited(s)
    assert "No matching data" in s["final_response"]


def test_clarification_branch(engine):
    s = run(FakeLLM([], needs_clarification=True))
    assert nodes_visited(s) == ["understand_question", "generate_response"]
    assert "clarification" in s["final_response"].lower()


class CrashingLLM:
    """Simulates an LLM API error (bad key, unsupported parameter, outage)."""

    def structured(self, schema, system, user):
        raise ValueError("simulated API error")


def test_llm_error_stops_instead_of_looping(engine):
    s = run(CrashingLLM())
    assert nodes_visited(s) == ["understand_question", "generate_response"]
    assert "simulated API error" in s["final_response"]


def test_routers_directly():
    assert route_after_validate({"validation_status": "valid"}) == "execute_sql"
    assert route_after_validate({"validation_status": "invalid", "retry_count": 1}) == "generate_sql"
    assert route_after_validate({"validation_status": "invalid", "retry_count": 99}) == "generate_response"
    assert route_after_execute({"error_message": None, "row_count": 0}) == "generate_response"
    assert route_after_execute({"error_message": None, "row_count": 3}) == "analyze_results"
    assert route_after_validate({"validation_status": "invalid", "retry_count": 0,
                                 "failed_node": "generate_sql"}) == "generate_response"


# ----------------------------------------------------------------- Part B: real LLM
QUESTIONS = [
    ("What is my total revenue this month?", {"orders"}),
    ("Which are my top five products by revenue?", {"products", "order_items"}),
    ("Which city generates the highest revenue?", {"customers", "orders"}),
    ("Which customers have purchased more than once?", {"customers", "orders"}),
    ("Which payment method is most popular?", {"payments"}),
    ("Which products have low stock?", {"products"}),
    ("Which product category generates the highest profit?", {"products", "order_items"}),
]


@pytest.mark.skipif(not config.llm_configured(), reason="No LLM API key configured")
@pytest.mark.parametrize("question,expected_tables", QUESTIONS)
def test_real_llm_questions(engine, question, expected_tables):
    s = build_graph().invoke({"user_question": question, "trace": []})
    print(f"\nQ: {question}\nTables: {s.get('identified_tables')}\nSQL: {s.get('validated_sql')}\n"
          f"Rows: {s.get('row_count')}\n{s.get('final_response')}")
    assert expected_tables <= set(s["identified_tables"])
    assert s["validation_status"] == "valid"
    assert s["row_count"] > 0
    assert s.get("error_message") is None
    assert s["final_response"]
