"""
Synthetic data generator + loader (the "ingestion" step of this project).

Run:  python database/seed_data.py
- Idempotent: if customers already has rows, it does nothing.
- Deterministic: random.Random(42) -> identical data every run.
- Uses the ADMIN (owner) connection, because loading data is a write.
  The dashboard and AI use the read-only role instead.

Business rules encoded here (see README "Financial definitions"):
- order_items.unit_price = product price at time of sale; subtotal = qty * price
- orders.total_amount = SUM(order_items.subtotal)  (no tax/shipping/discounts)
- delivered / shipped / processing  -> one 'success' payment
      (sometimes preceded by a 'failed' attempt)
- pending   -> one 'pending' payment
- cancelled -> one 'failed' payment
- returned  -> one 'refunded' payment
"""
import os
import random
import sys
from datetime import date, timedelta
from decimal import Decimal

import psycopg

SEED = 42
N_CUSTOMERS = 120
N_ORDERS = 420
START = date(2026, 4, 1)
END = date(2026, 10, 29)

CITIES = [  # (city, state, weight)
    ("Pune", "Maharashtra", 18), ("Mumbai", "Maharashtra", 20),
    ("Bengaluru", "Karnataka", 17), ("Hyderabad", "Telangana", 11),
    ("Chennai", "Tamil Nadu", 9), ("Delhi", "Delhi", 12),
    ("Ahmedabad", "Gujarat", 5), ("Jaipur", "Rajasthan", 3),
    ("Kolkata", "West Bengal", 3), ("Lucknow", "Uttar Pradesh", 2),
]
FIRST = ["Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Krishna",
         "Ishaan", "Rohan", "Ananya", "Diya", "Aadhya", "Saanvi", "Kavya", "Isha",
         "Meera", "Priya", "Riya", "Neha", "Kabir", "Dev", "Tanvi", "Pooja", "Nikhil"]
LAST = ["Sharma", "Patil", "Iyer", "Reddy", "Nair", "Kulkarni", "Deshmukh", "Gupta",
        "Mehta", "Joshi", "Rao", "Singh", "Shah", "Das", "Menon", "Kapoor", "Bhat"]

PRODUCTS = [  # (name, category, unit_price, cost_price, stock)
    ("Wireless Earbuds Pro", "Electronics", 2999, 1650, 85),
    ("Smart Fitness Band", "Electronics", 1999, 1150, 12),
    ("Bluetooth Speaker Mini", "Electronics", 1499, 820, 64),
    ("USB-C Fast Charger 30W", "Electronics", 899, 420, 140),
    ("Noise Cancelling Headphones", "Electronics", 7499, 4800, 8),
    ("Mechanical Keyboard", "Electronics", 3499, 2100, 30),
    ("Non-Stick Cookware Set", "Home & Kitchen", 2499, 1400, 40),
    ("Steel Water Bottle 1L", "Home & Kitchen", 549, 210, 220),
    ("Electric Kettle 1.5L", "Home & Kitchen", 1299, 760, 55),
    ("Cotton Bedsheet Set", "Home & Kitchen", 1199, 560, 6),
    ("Air Fryer 4L", "Home & Kitchen", 5499, 3700, 18),
    ("Men's Running Shoes", "Fashion", 2799, 1300, 70),
    ("Women's Denim Jacket", "Fashion", 2199, 980, 25),
    ("Cotton T-Shirt Pack (3)", "Fashion", 999, 380, 180),
    ("Leather Wallet", "Fashion", 799, 300, 9),
    ("Data Engineering Handbook", "Books", 899, 450, 60),
    ("Python for Analysts", "Books", 699, 330, 75),
    ("Business Strategy Essentials", "Books", 599, 280, 4),
    ("Yoga Mat Premium", "Sports & Fitness", 1299, 560, 95),
    ("Adjustable Dumbbell 10kg", "Sports & Fitness", 3299, 2300, 14),
    ("Cricket Bat English Willow", "Sports & Fitness", 4999, 3100, 11),
    ("Herbal Face Wash", "Beauty", 349, 120, 300),
    ("Vitamin C Serum", "Beauty", 799, 260, 150),
    ("Hair Dryer Compact", "Beauty", 1599, 950, 3),
]
STATUSES = [("delivered", 60), ("shipped", 10), ("processing", 6),
            ("pending", 6), ("cancelled", 10), ("returned", 8)]
METHODS = [("upi", 40), ("credit_card", 20), ("debit_card", 15),
           ("cash_on_delivery", 10), ("net_banking", 8), ("wallet", 7)]


def pick(rng, weighted):
    items, weights = zip(*weighted)
    return rng.choices(items, weights=weights, k=1)[0]


def rand_date(rng, start, end):
    return start + timedelta(days=rng.randint(0, (end - start).days))


def generate():
    rng = random.Random(SEED)

    customers = []
    for cid in range(1, N_CUSTOMERS + 1):
        city, state = pick(rng, [((c, s), w) for c, s, w in CITIES])
        fn, ln = rng.choice(FIRST), rng.choice(LAST)
        customers.append((cid, f"{fn} {ln}", f"{fn.lower()}.{ln.lower()}{cid}@example.com",
                          city, state, rand_date(rng, date(2025, 10, 1), date(2026, 9, 30))))

    products = [(i + 1, n, c, Decimal(p), Decimal(cp), s)
                for i, (n, c, p, cp, s) in enumerate(PRODUCTS)]
    # Popularity weights so some products clearly sell more than others.
    pop = [rng.choice([1, 2, 3, 5, 8]) for _ in products]
    # A subset of loyal customers who order often -> repeat-customer analysis.
    cust_weight = [rng.choice([1, 1, 1, 2, 4]) for _ in customers]

    # Order dates: growth trend (later months get more orders).
    day_span = (END - START).days
    day_weights = [1 + 1.5 * d / day_span for d in range(day_span + 1)]

    orders, items, payments = [], [], []
    item_id = pay_id = 0
    for oid in range(1, N_ORDERS + 1):
        cust = rng.choices(customers, weights=cust_weight, k=1)[0]
        odate = START + timedelta(days=rng.choices(range(day_span + 1), weights=day_weights, k=1)[0])
        if odate < cust[5]:              # cannot order before registering
            odate = max(cust[5], START)
            if odate > END:
                odate = END
        recent = (END - odate).days <= 6
        status = pick(rng, [("pending", 3), ("processing", 3), ("shipped", 3), ("delivered", 1)]) \
            if recent else pick(rng, STATUSES)

        lines = rng.sample(range(len(products)), k=rng.choices([1, 2, 3, 4], weights=[35, 35, 20, 10])[0])
        total = Decimal("0")
        for idx in lines:
            p = products[idx]
            qty = rng.choices([1, 2, 3], weights=[70, 22, 8])[0]
            sub = p[3] * qty
            item_id += 1
            items.append((item_id, oid, p[0], qty, p[3], sub))
            total += sub
        orders.append((oid, cust[0], odate, status, total))

        method = pick(rng, METHODS)
        if status in ("delivered", "shipped", "processing"):
            if method != "cash_on_delivery" and rng.random() < 0.15:
                pay_id += 1
                payments.append((pay_id, oid, odate, method, "failed", total))
                method = pick(rng, [m for m in METHODS if m[0] != "cash_on_delivery"])
            pay_id += 1
            payments.append((pay_id, oid, odate + timedelta(days=rng.randint(0, 1)), method, "success", total))
        elif status == "pending":
            pay_id += 1
            payments.append((pay_id, oid, odate, method, "pending", total))
        elif status == "cancelled":
            pay_id += 1
            payments.append((pay_id, oid, odate, method if method != "cash_on_delivery" else "upi", "failed", total))
        elif status == "returned":
            pay_id += 1
            payments.append((pay_id, oid, odate + timedelta(days=rng.randint(5, 12)), method, "refunded", total))

    return customers, products, orders, items, payments


def admin_conninfo():
    return (f"host={os.getenv('DB_HOST', 'localhost')} port={os.getenv('DB_PORT', '5432')} "
            f"dbname={os.environ['POSTGRES_DB']} user={os.environ['POSTGRES_USER']} "
            f"password={os.environ['POSTGRES_PASSWORD']}")


def main():
    with psycopg.connect(admin_conninfo()) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM customers")
            if cur.fetchone()[0] > 0:
                print("Seed skipped: data already present.")
                return
            customers, products, orders, items, payments = generate()
            cur.executemany("INSERT INTO customers VALUES (%s,%s,%s,%s,%s,%s)", customers)
            cur.executemany("INSERT INTO products VALUES (%s,%s,%s,%s,%s,%s)", products)
            cur.executemany("INSERT INTO orders VALUES (%s,%s,%s,%s,%s)", orders)
            cur.executemany("INSERT INTO order_items VALUES (%s,%s,%s,%s,%s,%s)", items)
            cur.executemany("INSERT INTO payments VALUES (%s,%s,%s,%s,%s,%s)", payments)
            # Explicit IDs were inserted, so move each SERIAL sequence past them.
            for t, col in [("customers", "customer_id"), ("products", "product_id"), ("orders", "order_id"),
                           ("order_items", "order_item_id"), ("payments", "payment_id")]:
                cur.execute(f"SELECT setval(pg_get_serial_sequence('{t}', '{col}'), (SELECT MAX({col}) FROM {t}))")
        conn.commit()  # one transaction: all rows load, or none do
    print(f"Seeded {len(customers)} customers, {len(products)} products, {len(orders)} orders, "
          f"{len(items)} order_items, {len(payments)} payments.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # make failures obvious in `docker compose logs`
        print(f"SEED FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
