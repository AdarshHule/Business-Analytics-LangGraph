# Business Intelligence Platform: Overview for the Business Owner

*This uses a fictional store with made-up (synthetic) data. The numbers show how the system works; they are not real business results.*

## Why does a business need a database?
Every sale creates information: who bought, what they bought, how much they paid and whether the payment worked.
In spreadsheets this information gets copied, mistyped and scattered. A **database** keeps one trusted copy, checks
every new record against rules, and can answer questions in seconds.

## Why five tables?
Each table holds **one kind of thing**, like separate registers in a shop:

| Table | Think of it as… | Example |
|---|---|---|
| **Customers** | the customer register | Priya Sharma, Pune |
| **Products** | the price list and stock book | Air Fryer, ₹5,499, 18 in stock |
| **Orders** | the order book | Order #105, Priya, 12 Sep, *delivered* |
| **Order items** | the lines on each bill | 1 Air Fryer + 2 Water Bottles |
| **Payments** | the payment record | UPI ₹6,597: failed, then card: success |

Keeping them separate means a customer's address is written **once**. If it changes, it changes everywhere.

## How do the tables connect?
Each record carries a **reference number** to the record it belongs to:
- An order carries the **customer's number**.
- Each bill line carries the **order number** and the **product number**.
- Each payment carries the **order number**.

The database **refuses** anything that doesn't fit, such as an order for a customer who doesn't exist, a negative price, or a
bill line whose total doesn't equal quantity × price. Mistakes are stopped at entry.

## How is a sale represented?
Priya buys an Air Fryer and two bottles → **1 row** in Orders, **2 rows** in Order items, and **1 or more rows** in Payments
(one per attempt). Revenue counts only completed orders (processing, shipped or delivered), and it is counted from the order, so a
failed-then-successful payment is never counted twice.

## How does it run? (Docker)
The whole system runs in two sealed "boxes" called **containers**: one for the database and one for the dashboard.
One command starts both on any computer, identically. The data is kept in a separate storage area (a **volume**), so it
survives restarts.

## How does PostgreSQL store and SQL retrieve information?
**PostgreSQL** is the database engine that stores the tables safely on disk. **SQL** is the language for asking it questions.
For example, "add up the bill lines of completed orders, grouped by city" gives revenue by city.

## How does the AI answer questions? (LangGraph)
You type a question like *"Which city generates the highest revenue?"* The system works through seven checked steps:
1. Understand the question.
2. Find which tables hold the answer.
3. Write a database query.
4. **Safety check:** the query must only *read*. It can never change or delete anything.
5. Run it on the real data.
6. Explain the actual results. It is instructed to use only those numbers and never to guess.
7. Show you the answer, the query it ran, the data table and a chart.

If a step fails, it fixes itself up to two times, then tells you honestly that it couldn't answer.
Even if the AI made a mistake, the database account it uses **does not have permission to change data**.

## What does the dashboard show?
Revenue, orders, customers, average order value, gross profit and margin, plus pages for sales, products,
customers, orders and payments. You can filter by date, product category and city.

## What decisions can it support?
Examples found in this sample data:
- **Pricing and promotion:** Electronics brings the most revenue (38%), but Fashion has the best margin (56% vs 40%), so promote
  high-margin categories.
- **Stock:** 8 products are below 15 units, including fast sellers, so reorder before they sell out.
- **Payments:** debit card attempts fail about twice as often as wallet payments, so check that payment gateway.
- **Customers:** repeat buyers produce 93% of revenue, so a loyalty programme is worth considering.
- **Markets:** Mumbai and Pune give 44% of revenue, so protect them and test campaigns in smaller cities.
- **Losses:** cancellations and returns are 16% of order value. Start recording the reasons.
