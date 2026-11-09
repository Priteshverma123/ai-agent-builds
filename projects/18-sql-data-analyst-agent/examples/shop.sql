-- A tiny online shop used by the demo and the tests.
-- Revenue is only counted for orders with status = 'paid'.

CREATE TABLE customers (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    country     TEXT    NOT NULL,
    signup_date TEXT    NOT NULL
);

CREATE TABLE products (
    id       INTEGER PRIMARY KEY,
    name     TEXT    NOT NULL,
    category TEXT    NOT NULL,
    price    REAL    NOT NULL
);

CREATE TABLE orders (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_date  TEXT    NOT NULL,
    status      TEXT    NOT NULL CHECK (status IN ('paid', 'refunded'))
);

CREATE TABLE order_items (
    order_id   INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   INTEGER NOT NULL,
    unit_price REAL    NOT NULL
);

INSERT INTO customers VALUES
    (1, 'Asha Rao',    'India',   '2025-11-03'),
    (2, 'Ben Carter',  'USA',     '2025-12-10'),
    (3, 'Clara Weiss', 'Germany', '2026-01-05'),
    (4, 'Diego Lima',  'Brazil',  '2026-01-20'),
    (5, 'Emma Hughes', 'UK',      '2026-02-02'),
    (6, 'Farhan Ali',  'India',   '2026-02-14'),
    (7, 'Grace Kim',   'USA',     '2026-03-09'),
    (8, 'Hugo Becker', 'Germany', '2026-04-01');

INSERT INTO products VALUES
    (1, 'Mechanical Keyboard',      'Hardware',  89.00),
    (2, 'USB-C Dock',               'Hardware', 129.00),
    (3, 'Noise-Cancelling Headset', 'Audio',    149.00),
    (4, 'Desk Mic',                 'Audio',     59.00),
    (5, 'Cloud Backup (1yr)',       'Software',  49.00),
    (6, 'Code Editor Pro (1yr)',    'Software',  79.00);

INSERT INTO orders VALUES
    ( 1, 1, '2026-01-08', 'paid'),
    ( 2, 2, '2026-01-15', 'paid'),
    ( 3, 3, '2026-01-22', 'paid'),
    ( 4, 4, '2026-02-03', 'paid'),
    ( 5, 1, '2026-02-11', 'refunded'),
    ( 6, 5, '2026-02-19', 'paid'),
    ( 7, 6, '2026-03-02', 'paid'),
    ( 8, 2, '2026-03-12', 'paid'),
    ( 9, 7, '2026-03-25', 'paid'),
    (10, 3, '2026-04-04', 'paid'),
    (11, 8, '2026-04-15', 'paid'),
    (12, 4, '2026-04-28', 'refunded'),
    (13, 5, '2026-05-06', 'paid'),
    (14, 6, '2026-05-17', 'paid'),
    (15, 7, '2026-05-29', 'paid'),
    (16, 1, '2026-06-03', 'paid'),
    (17, 8, '2026-06-14', 'paid'),
    (18, 2, '2026-06-26', 'paid');

INSERT INTO order_items VALUES
    ( 1, 1, 1,  89.00), ( 1, 5, 1,  49.00),
    ( 2, 3, 1, 149.00),
    ( 3, 2, 1, 129.00), ( 3, 1, 1,  89.00),
    ( 4, 6, 2,  79.00),
    ( 5, 4, 1,  59.00),
    ( 6, 3, 1, 149.00), ( 6, 4, 1,  59.00),
    ( 7, 5, 3,  49.00),
    ( 8, 2, 2, 129.00),
    ( 9, 1, 1,  89.00), ( 9, 6, 1,  79.00),
    (10, 3, 2, 149.00),
    (11, 2, 1, 129.00),
    (12, 1, 1,  89.00),
    (13, 6, 1,  79.00), (13, 5, 1,  49.00),
    (14, 3, 1, 149.00),
    (15, 2, 1, 129.00), (15, 4, 2,  59.00),
    (16, 1, 2,  89.00),
    (17, 3, 1, 149.00), (17, 6, 1,  79.00),
    (18, 5, 2,  49.00);
