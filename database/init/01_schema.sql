-- =====================================================================
-- business_analytics schema  (PostgreSQL 16)
-- Runs automatically the FIRST time the db container starts with an
-- empty volume (files in /docker-entrypoint-initdb.d run in name order).
--
-- Relationships (all one-to-many):
--   customers 1 ── * orders        (a customer places many orders)
--   orders    1 ── * order_items   (an order contains many lines)
--   products  1 ── * order_items   (a product appears on many lines)
--   orders    1 ── * payments      (an order can have several payment
--                                   attempts, e.g. failed then success)
-- =====================================================================

CREATE TABLE customers (
    customer_id        SERIAL        PRIMARY KEY,
    customer_name      VARCHAR(100)  NOT NULL,
    email              VARCHAR(150)  NOT NULL UNIQUE,
    city               VARCHAR(60)   NOT NULL,
    state              VARCHAR(60)   NOT NULL,
    registration_date  DATE          NOT NULL,
    CONSTRAINT chk_customers_email CHECK (email LIKE '%_@_%._%')
);

CREATE TABLE products (
    product_id      SERIAL         PRIMARY KEY,
    product_name    VARCHAR(120)   NOT NULL UNIQUE,
    category        VARCHAR(50)    NOT NULL,
    unit_price      NUMERIC(10,2)  NOT NULL CHECK (unit_price > 0),
    cost_price      NUMERIC(10,2)  NOT NULL CHECK (cost_price >= 0),
    stock_quantity  INTEGER        NOT NULL CHECK (stock_quantity >= 0),
    CONSTRAINT chk_products_cost_le_price CHECK (cost_price <= unit_price)
);

CREATE TABLE orders (
    order_id      SERIAL         PRIMARY KEY,
    customer_id   INTEGER        NOT NULL REFERENCES customers(customer_id),
    order_date    DATE           NOT NULL,
    order_status  VARCHAR(20)    NOT NULL CHECK (order_status IN
                  ('pending','processing','shipped','delivered','cancelled','returned')),
    total_amount  NUMERIC(12,2)  NOT NULL CHECK (total_amount >= 0)
);

CREATE TABLE order_items (
    order_item_id  SERIAL         PRIMARY KEY,
    order_id       INTEGER        NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id     INTEGER        NOT NULL REFERENCES products(product_id),
    quantity       INTEGER        NOT NULL CHECK (quantity > 0),
    unit_price     NUMERIC(10,2)  NOT NULL CHECK (unit_price > 0),   -- price at time of sale
    subtotal       NUMERIC(12,2)  NOT NULL,
    CONSTRAINT chk_items_subtotal CHECK (subtotal = quantity * unit_price),
    CONSTRAINT uq_items_order_product UNIQUE (order_id, product_id) -- one line per product per order
);

CREATE TABLE payments (
    payment_id      SERIAL         PRIMARY KEY,
    order_id        INTEGER        NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    payment_date    DATE           NOT NULL,
    payment_method  VARCHAR(20)    NOT NULL CHECK (payment_method IN
                    ('credit_card','debit_card','upi','net_banking','wallet','cash_on_delivery')),
    payment_status  VARCHAR(20)    NOT NULL CHECK (payment_status IN
                    ('success','failed','pending','refunded')),
    amount          NUMERIC(12,2)  NOT NULL CHECK (amount > 0)
);

-- Indexes: PostgreSQL indexes primary keys automatically, but NOT foreign
-- keys. We index FK columns (used in every JOIN) and common filter columns.
CREATE INDEX idx_orders_customer_id     ON orders(customer_id);
CREATE INDEX idx_orders_order_date      ON orders(order_date);
CREATE INDEX idx_orders_status          ON orders(order_status);
CREATE INDEX idx_order_items_order_id   ON order_items(order_id);
CREATE INDEX idx_order_items_product_id ON order_items(product_id);
CREATE INDEX idx_payments_order_id      ON payments(order_id);
CREATE INDEX idx_payments_status        ON payments(payment_status);
CREATE INDEX idx_customers_city         ON customers(city);
CREATE INDEX idx_products_category      ON products(category);

COMMENT ON TABLE customers   IS 'People who registered with the store (one row per customer).';
COMMENT ON TABLE products    IS 'Product catalogue with selling price, cost price and stock.';
COMMENT ON TABLE orders      IS 'Order header: who ordered, when, status and order total.';
COMMENT ON TABLE order_items IS 'Order lines: which products and quantities are in each order.';
COMMENT ON TABLE payments    IS 'Payment attempts for orders (an order may have a failed then a successful attempt).';
