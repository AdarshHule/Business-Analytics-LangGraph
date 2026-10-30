# 5-Minute Demo Script (for Rahul)

**Before you start:** `docker compose ps` shows both containers healthy, http://localhost:8501 is open, and a Terminal is ready
in the project folder. Ask one AI question once beforehand so you know it works and how long it takes.

| Time | Do | Say (in your own words) |
|---|---|---|
| 0:00–0:30 | Executive Overview | "This is a BI platform for a fictional retail store. The owner can see performance, explore the database and ask questions in English. All data is synthetic." |
| 0:30–0:50 | stay | "The problem: business data is only useful if the owner can get trusted answers without writing SQL." |
| 0:50–1:20 | LangGraph Architecture page, or README architecture | "Two Docker containers: PostgreSQL and a Streamlit app. The app reads through a **read-only** database user. The AI part is a LangGraph workflow." |
| 1:20–2:00 | Database Explorer → ERD | "Five tables, all one-to-many. order_items resolves the many-to-many between orders and products. Foreign keys and CHECK constraints stop invalid data, for example subtotal must equal quantity × price." |
| 2:00–2:20 | Terminal: `docker compose ps` | "db and app are both healthy. The app only starts after the database health check passes. Data is in a named volume, so it survives restarts." |
| 2:20–3:00 | Executive → Sales → Products (low stock) | "Every number is a live SQL query. Revenue counts only processing, shipped and delivered orders, and it **reconciles exactly** with successful payments: ₹19.48 L. Eight products are low on stock." Change a filter to show it reacts. |
| 3:00–4:15 | AI Business Analyst → *"Which product category generates the highest profit?"* | Point at the live steps: "understand → identify tables → generate SQL → **validate** → execute → analyze → respond. Here is the exact SQL it ran, the validation result, the real rows and the chart." |
| 4:15–4:40 | (optional) type *"Delete all payments"* | "The validator rejects it, and even if it didn't, the database user has no write permission. I have tests for both." |
| 4:40–5:00 | Business Insights | "Each insight shows finding, meaning, supporting data and action. For example, Electronics is 38% of revenue but Fashion has the best margin. Next steps would be real data sources, scheduled ingestion and authentication." |

> On the "delete" question, the workflow may stop at step 1 as off-topic, or the validator may reject it. Either way nothing is
> deleted. Explain whichever happens. Don't promise a specific path.

---

## Likely questions and answers

**Why PostgreSQL?** It's an open-source relational database with strong integrity (foreign keys, CHECK constraints, ACID transactions),
good analytical SQL (CTEs, window functions, `FILTER`), and fine-grained roles. That last point lets the AI use a read-only account.

**Why five separate tables?** Normalization: each fact is stored once. Customer details aren't repeated on every order, and an order
can have many products and many payment attempts. This avoids update anomalies and inconsistent data.

**What is a primary key?** A column that uniquely identifies each row, never NULL, e.g. `order_id`. PostgreSQL indexes it automatically.

**What is a foreign key?** A column that must match a primary key in another table, e.g. `orders.customer_id → customers.customer_id`.
The database rejects orphans. That is **referential integrity**.

**What is normalization?** Organizing tables so each non-key column depends only on its table's key (up to 3NF): no repeating groups and
no duplicated facts. `order_items.unit_price` is a deliberate historical copy, the price at the time of sale.

**What is Docker? Docker Compose?** Docker packages an app with everything it needs into an **image**. A running image is a **container**.
Compose starts several containers together with their network, volumes and settings from one `docker-compose.yml`.

**What is a container volume?** Storage managed by Docker outside the container's filesystem. `pgdata` keeps the database files, so
`docker compose down` and `up` keep the data. `down -v` deletes it.

**What is LangGraph? StateGraph?** LangGraph builds LLM workflows as graphs with explicit control flow. A `StateGraph` is a graph whose
nodes share a typed state dictionary (`AnalystState`, a TypedDict).

**What are nodes and edges?** A node is a Python function that takes the state and returns a partial update. An edge says what runs next.
A **conditional edge** calls a routing function, e.g. after `validate_sql`: valid → execute, invalid with retries left → regenerate,
else → respond with an error.

**How does the LLM generate SQL?** `identify_tables` gives it only the relevant part of the **live schema** (read from PostgreSQL's
catalog), and the prompt includes the business rules (what counts as revenue, allowed status values). It returns a structured object
`{sql, explanation}`. On failure it receives its previous SQL and the exact error and tries again, at most 2 retries.

**How do you prevent unsafe SQL?** Three layers. (1) A sqlglot-based validator *parses* the query: one statement only, SELECT only, no write
or DDL nodes anywhere (even inside a CTE), only the 5 tables, no dangerous functions, LIMIT 200. (2) A read-only transaction. (3) The
PostgreSQL role `analytics_ro` has SELECT-only grants, read-only sessions and a 5-second timeout. Tests show DELETE fails with
"permission denied" even after switching the session to read-write.

**How does the app talk to PostgreSQL?** SQLAlchemy with the Psycopg driver connects to host `db` on the Compose network.
Credentials come from environment variables, and every query uses bound parameters.

**How are revenue and profit calculated?** Revenue is the sum of order-line subtotals for processing, shipped and delivered orders.
COGS is quantity × cost price. Gross profit = revenue − COGS, and margin = gross profit ÷ revenue. Revenue is not summed from payments, because
an order can have a failed and a successful payment row. Successful payments are used as a reconciliation check, and they match.

**What happens if the database is unavailable?** At startup the app waits for the DB health check. If the DB goes down later,
`main.py` pings it and shows a clear "cannot connect" message instead of crashing. In the AI workflow, a database error is caught,
retried, and then reported honestly.

**What would you improve next?** Scheduled incremental ingestion from a real source, historical cost prices, authentication,
caching of frequent questions, an evaluation set of questions with expected SQL for the AI, and conversation memory.

**What did you build vs. what was generated?** Answer honestly: you built it with Claude Code as a coding assistant. Then show you
understand it. Walk through `queries.py` (revenue rule), `sql_validator.py` and `graph.py` (routing functions).
