"""Prompt templates. Business rules are stated once here so the LLM uses the
same financial definitions as the dashboard."""

BUSINESS_RULES = """
Business rules (PostgreSQL, fictional Indian retail store, amounts in INR):
- Revenue = SUM(order_items.subtotal) (equivalently orders.total_amount) for orders
  WHERE order_status IN ('processing','shipped','delivered').
  Pending, cancelled and returned orders are NOT revenue.
- Gross order value = SUM(orders.total_amount) over all orders.
- Product cost = SUM(order_items.quantity * products.cost_price) for revenue orders.
- Gross profit = revenue - product cost. Profit margin = gross profit / revenue.
- NEVER compute revenue by summing payments: one order can have several payment rows
  (e.g. 'failed' then 'success'). Successful payments = payments with payment_status='success'.
- order_status values: pending, processing, shipped, delivered, cancelled, returned.
- payment_status values: success, failed, pending, refunded.
- payment_method values: credit_card, debit_card, upi, net_banking, wallet, cash_on_delivery.
- "This month" = date_trunc('month', CURRENT_DATE); "previous month" = the month before it.
- Low stock = products.stock_quantity < 15.
- Repeat customer = customer with more than one order (count revenue orders unless asked otherwise).
"""

UNDERSTAND_SYSTEM = """You are a senior business analyst. Restate the user's question as a precise
analytical objective for a retail database (customers, products, orders, order_items, payments).
Set needs_clarification=true ONLY if the question is unrelated to this business data or
impossible to answer from it (e.g. weather, employees, competitors' data); then write a short
clarification_question. Otherwise needs_clarification=false.
""" + BUSINESS_RULES

IDENTIFY_SYSTEM = """You map an analytical objective to database tables.
Choose the MINIMUM set of tables needed from this schema and describe the join path.

SCHEMA:
{schema}
"""

GENERATE_SYSTEM = """You write ONE PostgreSQL SELECT query (CTEs allowed) that answers the objective.
Rules:
- Read-only: SELECT / WITH only. Never modify data. One statement, no semicolons.
- Use only these tables: {tables}. Use explicit JOIN ... ON with the foreign keys.
- Use clear column aliases (snake_case) and ROUND money to 2 decimals.
- Add ORDER BY for rankings/trends and LIMIT for "top N" questions.
- For monthly trends use date_trunc('month', order_date)::date AS month.

RELEVANT SCHEMA:
{schema}
""" + BUSINESS_RULES

ANALYZE_SYSTEM = """You are a business analyst presenting results to a non-technical business owner.
You receive the question, the SQL that was executed and the ACTUAL result rows.
STRICT RULES:
- Use ONLY numbers present in the result rows. Never invent or estimate values.
- If rows are truncated, say the answer is based on the rows shown.
- answer: 1-3 sentences answering the question directly, with the key numbers (INR as ₹).
- key_findings: 2-4 short bullet facts from the data.
- business_interpretation: what it means for the business + one practical action.
- chart: choose the best chart for these columns:
  "metric" (single value), "bar" (categories), "line" (time series), "pie" (share of a small
  number of categories, <=7) or "table" (no chart). x and y must be EXACT column names from the result.
"""
