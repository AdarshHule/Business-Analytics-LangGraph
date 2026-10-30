import streamlit as st

from app import database as db
from app.components.erd import ERD_MERMAID, mermaid

DESCRIPTIONS = {
    "customers": "Who buys from us. One row per registered customer. Email is unique.",
    "products": "What we sell. Selling price, cost price (for profit) and current stock.",
    "orders": "The order header: which customer, when, its status and order total.",
    "order_items": "The order lines: which products and how many are in each order. "
                   "Stores the price at the time of sale.",
    "payments": "Money movements for an order. An order can have several attempts (e.g. failed, then success).",
}

EXAMPLES = {
    "Revenue by month": """SELECT date_trunc('month', order_date)::date AS month,
       SUM(total_amount) AS revenue
FROM orders
WHERE order_status IN ('processing','shipped','delivered')
GROUP BY 1 ORDER BY 1;""",
    "Top 5 products by revenue (3-table join)": """SELECT p.product_name, SUM(oi.subtotal) AS revenue
FROM order_items oi
JOIN orders o   ON o.order_id = oi.order_id
JOIN products p ON p.product_id = oi.product_id
WHERE o.order_status IN ('processing','shipped','delivered')
GROUP BY p.product_name
ORDER BY revenue DESC LIMIT 5;""",
    "Repeat customers": """SELECT c.customer_name, COUNT(o.order_id) AS orders
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(o.order_id) > 1
ORDER BY orders DESC;""",
    "Gross profit by category": """SELECT p.category,
       SUM(oi.subtotal) - SUM(oi.quantity * p.cost_price) AS gross_profit
FROM order_items oi
JOIN orders o   ON o.order_id = oi.order_id
JOIN products p ON p.product_id = oi.product_id
WHERE o.order_status IN ('processing','shipped','delivered')
GROUP BY p.category ORDER BY gross_profit DESC;""",
}


def render(_f=None) -> None:
    st.title("Database Explorer")
    st.caption("Everything on this page is read live from PostgreSQL's system catalog. No SQL needed.")
    counts = db.get_row_counts()
    cols, cons = db.get_columns(), db.get_constraints()

    st.subheader("1. Overview")
    st.markdown("Database **`business_analytics`** (PostgreSQL 16) with **5 related tables** for a fictional "
                "online retail store. All data is synthetic.")
    mc = st.columns(5)
    for c, r in zip(mc, counts.itertuples()):
        c.metric(r.table_name, f"{r.row_count:,} rows")

    st.subheader("2. Entity Relationship Diagram")
    mermaid(ERD_MERMAID, height=640)
    st.markdown("""
**How to read it:** `||--o{` means **one-to-many**. PK = primary key, FK = foreign key, UK = unique.

**How information flows when a customer buys:**
1. The customer exists in **customers** (once).
2. Checkout creates one row in **orders** pointing to that customer (`customer_id` FK).
3. Each product in the cart becomes one row in **order_items** pointing to the order and to the product.
4. Each payment attempt becomes a row in **payments** pointing to the order.

To answer "revenue by city" we follow the links: order_items → orders → customers.
""")
    with st.expander("Mermaid source"):
        st.code(ERD_MERMAID, language="text")

    st.subheader("3. Tables")
    for t in db.TABLES:
        n = int(counts.set_index("table_name").loc[t, "row_count"])
        with st.expander(f"**{t}** · {n:,} rows · {DESCRIPTIONS[t]}"):
            tc = cols[cols.table_name == t][["column_name", "data_type", "size", "is_nullable"]]
            keys = cons[cons.table_name == t]
            pk = keys[keys.constraint_type == "PRIMARY KEY"].definition.str.extract(r"\((\w+)\)")[0].tolist()
            fk = dict(keys[keys.constraint_type == "FOREIGN KEY"].definition.str.extract(
                r"KEY \((\w+)\) (REFERENCES \w+\(\w+\))").values.tolist())
            tc = tc.assign(key=tc.column_name.map(lambda c: "PK" if c in pk else ("FK → " + fk[c].replace("REFERENCES ", "")
                                                                                 if c in fk else "")))
            st.markdown("**Columns**")
            st.dataframe(tc, width="stretch", hide_index=True)
            st.markdown("**Constraints** (rules PostgreSQL enforces on every insert/update)")
            st.dataframe(keys[["constraint_type", "constraint_name", "definition"]], width="stretch",
                         hide_index=True)
            st.markdown("**Sample records**")
            st.dataframe(db.sample_rows(t, 8), width="stretch", hide_index=True)

    st.subheader("4. Relationships")
    st.dataframe(cons[cons.constraint_type == "FOREIGN KEY"][["table_name", "definition"]]
                 .rename(columns={"table_name": "child table"}), width="stretch", hide_index=True)
    st.markdown("""
| Parent (one) | Child (many) | Meaning |
|---|---|---|
| customers | orders | A customer can place many orders; each order belongs to one customer. |
| orders | order_items | An order has one or more lines; each line belongs to one order. |
| products | order_items | A product can appear in many orders' lines. |
| orders | payments | An order can have several payment attempts. |

`orders` ↔ `products` is **many-to-many** (an order has many products, a product is in many orders);
`order_items` is the **junction table** that resolves it.
""")

    st.subheader("5. Example SQL queries")
    choice = st.selectbox("Pick an example", list(EXAMPLES))
    st.code(EXAMPLES[choice], language="sql")
    if st.button("Run this example (read-only)"):
        st.dataframe(db.run_query(EXAMPLES[choice].rstrip(";")), width="stretch", hide_index=True)

    st.subheader("6. Design explanation")
    st.markdown("""
**Normalization (up to 3rd Normal Form).** Each fact is stored once, in the table it describes:
- Customer details live only in `customers`. If a customer moves city we update **one** row, not every order.
- Product prices live in `products`. `order_items.unit_price` is a deliberate copy: the **price at the time of
  sale**, which must not change when the catalogue price changes later.
- No repeating groups: instead of `product1, product2, ...` columns in orders, each product is a row in `order_items`.

**Why separate tables?** It avoids duplication and update anomalies, keeps the data consistent and makes
any combination answerable with JOINs.

**Referential integrity.** Foreign keys mean PostgreSQL **refuses** an order for a customer that does not exist,
or an order line for an unknown product. CHECK constraints refuse invalid values (negative prices, unknown
statuses, `subtotal ≠ quantity × unit_price`). Bad data is stopped at the door, not cleaned up later.

**Indexes** on foreign keys and date/status columns speed up the JOINs and filters the dashboard uses.
""")
