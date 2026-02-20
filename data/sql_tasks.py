"""Bird-Bench-style NL→SQL tasks for the sema4-demo SQL gen agent eval."""

import hashlib
import json
import sqlite3

DB_SCHEMA_DESC = """
Tables:
  customers(id INTEGER, name TEXT, plan_id INTEGER, monthly_spend REAL, status TEXT, data_used_gb REAL)
  transactions(id INTEGER, customer_id INTEGER, amount REAL, date TEXT, type TEXT)
  plans(id INTEGER, name TEXT, data_limit_gb REAL, price REAL)

Relationships:
  customers.plan_id → plans.id
  transactions.customer_id → customers.id

Notes:
  - status values: 'active', 'suspended', 'cancelled'
  - transaction type values: 'charge', 'payment', 'refund'
  - dates are ISO format: YYYY-MM-DD
  - data_used_gb is usage for the current billing month
"""


def _result_hash(rows: list) -> str:
    return hashlib.md5(json.dumps(rows, sort_keys=True).encode()).hexdigest()


TASKS = [
    {
        "id": "sql_001",
        "question": "Which customers have exceeded their plan's data limit this month?",
        "db_schema_desc": DB_SCHEMA_DESC,
        "expected_sql": """
SELECT c.id, c.name, c.data_used_gb, p.data_limit_gb
FROM customers c
JOIN plans p ON c.plan_id = p.id
WHERE c.data_used_gb > p.data_limit_gb
ORDER BY (c.data_used_gb - p.data_limit_gb) DESC
""".strip(),
        "expected_result_hash": None,
    },
    {
        "id": "sql_002",
        "question": "What is the total revenue from charges last month (2024-12)?",
        "db_schema_desc": DB_SCHEMA_DESC,
        "expected_sql": """
SELECT SUM(amount) AS total_revenue
FROM transactions
WHERE type = 'charge'
  AND date LIKE '2024-12-%'
""".strip(),
        "expected_result_hash": None,
    },
    {
        "id": "sql_003",
        "question": "Find the top 3 plans by number of active customers.",
        "db_schema_desc": DB_SCHEMA_DESC,
        "expected_sql": """
SELECT p.name, COUNT(c.id) AS active_customers
FROM plans p
JOIN customers c ON c.plan_id = p.id
WHERE c.status = 'active'
GROUP BY p.id, p.name
ORDER BY active_customers DESC
LIMIT 3
""".strip(),
        "expected_result_hash": None,
    },
    {
        "id": "sql_004",
        "question": "How many customers are on each status?",
        "db_schema_desc": DB_SCHEMA_DESC,
        "expected_sql": """
SELECT status, COUNT(*) AS count
FROM customers
GROUP BY status
ORDER BY count DESC
""".strip(),
        "expected_result_hash": None,
    },
    {
        "id": "sql_005",
        "question": "Which customers have spent more than their plan's monthly price in the last 30 days?",
        "db_schema_desc": DB_SCHEMA_DESC,
        "expected_sql": """
SELECT c.id, c.name, SUM(t.amount) AS total_charges, p.price AS plan_price
FROM customers c
JOIN plans p ON c.plan_id = p.id
JOIN transactions t ON t.customer_id = c.id
WHERE t.type = 'charge'
  AND t.date >= date('now', '-30 days')
GROUP BY c.id, c.name, p.price
HAVING SUM(t.amount) > p.price
ORDER BY total_charges DESC
""".strip(),
        "expected_result_hash": None,
    },
    {
        "id": "sql_006",
        "question": "What is the average monthly spend per plan?",
        "db_schema_desc": DB_SCHEMA_DESC,
        "expected_sql": """
SELECT p.name, AVG(c.monthly_spend) AS avg_spend
FROM plans p
JOIN customers c ON c.plan_id = p.id
GROUP BY p.id, p.name
ORDER BY avg_spend DESC
""".strip(),
        "expected_result_hash": None,
    },
    {
        "id": "sql_007",
        "question": "List customers who have made no transactions in the past 90 days.",
        "db_schema_desc": DB_SCHEMA_DESC,
        "expected_sql": """
SELECT c.id, c.name, c.status
FROM customers c
WHERE c.id NOT IN (
    SELECT DISTINCT customer_id
    FROM transactions
    WHERE date >= date('now', '-90 days')
)
ORDER BY c.name
""".strip(),
        "expected_result_hash": None,
    },
    {
        "id": "sql_008",
        "question": "Which plan has the highest average data usage relative to its limit?",
        "db_schema_desc": DB_SCHEMA_DESC,
        "expected_sql": """
SELECT p.name,
       AVG(c.data_used_gb) AS avg_used,
       p.data_limit_gb,
       AVG(c.data_used_gb) / p.data_limit_gb AS usage_ratio
FROM plans p
JOIN customers c ON c.plan_id = p.id
GROUP BY p.id, p.name, p.data_limit_gb
ORDER BY usage_ratio DESC
LIMIT 1
""".strip(),
        "expected_result_hash": None,
    },
    {
        "id": "sql_009",
        "question": "Find customers whose most recent transaction was a refund.",
        "db_schema_desc": DB_SCHEMA_DESC,
        "expected_sql": """
SELECT c.id, c.name, t.date, t.amount
FROM customers c
JOIN transactions t ON t.customer_id = c.id
WHERE t.id = (
    SELECT id FROM transactions
    WHERE customer_id = c.id
    ORDER BY date DESC
    LIMIT 1
)
  AND t.type = 'refund'
ORDER BY c.name
""".strip(),
        "expected_result_hash": None,
    },
    {
        "id": "sql_010",
        "question": "Show total charges vs payments per customer for 2024, only for active customers.",
        "db_schema_desc": DB_SCHEMA_DESC,
        "expected_sql": """
SELECT
    c.id,
    c.name,
    SUM(CASE WHEN t.type = 'charge' THEN t.amount ELSE 0 END) AS total_charges,
    SUM(CASE WHEN t.type = 'payment' THEN t.amount ELSE 0 END) AS total_payments
FROM customers c
JOIN transactions t ON t.customer_id = c.id
WHERE c.status = 'active'
  AND t.date LIKE '2024-%'
GROUP BY c.id, c.name
ORDER BY total_charges DESC
""".strip(),
        "expected_result_hash": None,
    },
    {
        "id": "sql_011",
        "question": "Which 5 customers have the highest data overage this month?",
        "db_schema_desc": DB_SCHEMA_DESC,
        "expected_sql": """
SELECT c.id, c.name, (c.data_used_gb - p.data_limit_gb) AS overage_gb
FROM customers c
JOIN plans p ON c.plan_id = p.id
WHERE c.data_used_gb > p.data_limit_gb
ORDER BY overage_gb DESC
LIMIT 5
""".strip(),
        "expected_result_hash": None,
    },
    {
        "id": "sql_012",
        "question": "What percentage of customers are on each plan?",
        "db_schema_desc": DB_SCHEMA_DESC,
        "expected_sql": """
SELECT p.name,
       COUNT(c.id) AS customer_count,
       ROUND(100.0 * COUNT(c.id) / (SELECT COUNT(*) FROM customers), 2) AS pct
FROM plans p
LEFT JOIN customers c ON c.plan_id = p.id
GROUP BY p.id, p.name
ORDER BY customer_count DESC
""".strip(),
        "expected_result_hash": None,
    },
]


def setup_db(path: str) -> None:
    """Create and seed a demo SQLite database at the given path."""
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    cur.executescript("""
        DROP TABLE IF EXISTS transactions;
        DROP TABLE IF EXISTS customers;
        DROP TABLE IF EXISTS plans;

        CREATE TABLE plans (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            data_limit_gb REAL NOT NULL,
            price REAL NOT NULL
        );

        CREATE TABLE customers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            plan_id INTEGER REFERENCES plans(id),
            monthly_spend REAL DEFAULT 0,
            status TEXT DEFAULT 'active',
            data_used_gb REAL DEFAULT 0
        );

        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER REFERENCES customers(id),
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            type TEXT NOT NULL
        );
    """)

    plans = [
        (1, "Starter",    5.0,   29.99),
        (2, "Plus",       20.0,  49.99),
        (3, "Pro",        50.0,  79.99),
        (4, "Unlimited",  999.0, 99.99),
    ]
    cur.executemany("INSERT INTO plans VALUES (?,?,?,?)", plans)

    customers = [
        (1,  "Alice Chen",     2, 55.00,  "active",    18.5),
        (2,  "Bob Torres",     1, 32.00,  "active",    6.2),   # over limit
        (3,  "Carol White",    3, 80.00,  "active",    45.0),
        (4,  "Dan Kim",        4, 102.00, "active",    120.0),
        (5,  "Eva Martinez",   2, 48.00,  "active",    22.1),  # over limit
        (6,  "Frank Lee",      1, 15.00,  "suspended", 0.0),
        (7,  "Grace Patel",    3, 75.00,  "active",    38.0),
        (8,  "Hiro Tanaka",    2, 60.00,  "active",    19.9),
        (9,  "Iris Johnson",   1, 29.99,  "active",    4.5),
        (10, "Jack Wilson",    4, 99.99,  "active",    200.0),
        (11, "Karen Brown",    3, 70.00,  "cancelled", 0.0),
        (12, "Luis Gomez",     2, 52.00,  "active",    21.0),  # over limit
        (13, "Maya Singh",     1, 5.00,   "suspended", 0.5),
        (14, "Nate Davis",     4, 110.00, "active",    350.0),
        (15, "Olivia Scott",   3, 82.00,  "active",    55.0),  # over limit
    ]
    cur.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?)", customers)

    transactions = [
        # customer 1 - Alice
        (1,  1,  49.99, "2024-12-01", "charge"),
        (2,  1,  49.99, "2024-11-01", "charge"),
        (3,  1,  49.99, "2024-12-01", "payment"),
        # customer 2 - Bob (over data limit)
        (4,  2,  29.99, "2024-12-01", "charge"),
        (5,  2,  29.99, "2024-11-01", "charge"),
        (6,  2,  29.99, "2024-12-01", "payment"),
        # customer 3 - Carol
        (7,  3,  79.99, "2024-12-01", "charge"),
        (8,  3,  10.00, "2024-12-15", "refund"),
        # customer 4 - Dan
        (9,  4,  99.99, "2024-12-01", "charge"),
        (10, 4,  99.99, "2024-11-01", "charge"),
        (11, 4,  99.99, "2024-10-01", "charge"),
        # customer 5 - Eva
        (12, 5,  49.99, "2024-12-01", "charge"),
        (13, 5,  15.00, "2024-12-20", "charge"),
        # customer 7 - Grace
        (14, 7,  79.99, "2024-12-01", "charge"),
        (15, 7,  79.99, "2024-12-01", "payment"),
        # customer 8 - Hiro
        (16, 8,  49.99, "2024-12-01", "charge"),
        # customer 9 - Iris
        (17, 9,  29.99, "2024-12-01", "charge"),
        # customer 10 - Jack
        (18, 10, 99.99, "2024-12-01", "charge"),
        (19, 10, 99.99, "2024-11-01", "charge"),
        # customer 12 - Luis
        (20, 12, 49.99, "2024-12-01", "charge"),
        (21, 12, 49.99, "2024-12-01", "payment"),
        # customer 14 - Nate
        (22, 14, 99.99, "2024-12-01", "charge"),
        (23, 14, 20.00, "2024-12-10", "charge"),
        # customer 15 - Olivia
        (24, 15, 79.99, "2024-12-01", "charge"),
        (25, 15, 79.99, "2024-12-01", "payment"),
    ]
    cur.executemany("INSERT INTO transactions VALUES (?,?,?,?,?)", transactions)

    conn.commit()
    conn.close()
