"""
Create a sample SQLite database for testing VeriSQL.
"""

import os
import sqlite3


def create_sample_database(db_path: str = "sample_store.db"):
    """Create a sample e-commerce database for testing."""
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.executescript(
        """
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            stock_quantity INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE customers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            city TEXT,
            is_test BOOLEAN DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            order_date TEXT NOT NULL,
            total_amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );

        CREATE TABLE order_items (
            id INTEGER PRIMARY KEY,
            order_id INTEGER,
            product_id INTEGER,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );

        INSERT INTO products (name, category, price, is_active, stock_quantity) VALUES
            ('Laptop Pro', 'Electronics', 1299.99, 1, 50),
            ('Wireless Mouse', 'Electronics', 29.99, 1, 200),
            ('USB-C Hub', 'Electronics', 49.99, 1, 150),
            ('Mechanical Keyboard', 'Electronics', 89.99, 1, 75),
            ('Monitor 27"', 'Electronics', 399.99, 1, 30),
            ('Webcam HD', 'Electronics', 79.99, 0, 0),
            ('Office Chair', 'Furniture', 249.99, 1, 25),
            ('Standing Desk', 'Furniture', 499.99, 1, 15),
            ('Desk Lamp', 'Furniture', 39.99, 1, 100),
            ('Notebook Set', 'Office', 12.99, 1, 500),
            ('Pen Pack', 'Office', 8.99, 1, 1000),
            ('Discontinued Item', 'Other', 9.99, 0, 0);

        INSERT INTO customers (name, email, city, is_test) VALUES
            ('Alice Johnson', 'alice@example.com', 'New York', 0),
            ('Bob Smith', 'bob@example.com', 'Los Angeles', 0),
            ('Charlie Brown', 'charlie@example.com', 'Chicago', 0),
            ('Diana Ross', 'diana@example.com', 'Houston', 0),
            ('Edward Chen', 'edward@example.com', 'Phoenix', 0),
            ('Test User', 'test@test.com', 'Test City', 1),
            ('Fiona Green', 'fiona@example.com', 'Philadelphia', 0),
            ('George Wilson', 'george@example.com', 'San Antonio', 0);

        INSERT INTO orders (customer_id, order_date, total_amount, status) VALUES
            (1, '2024-07-15', 1349.98, 'completed'),
            (2, '2024-07-20', 119.98, 'completed'),
            (3, '2024-08-01', 539.98, 'completed'),
            (4, '2024-08-15', 29.99, 'cancelled'),
            (5, '2024-08-25', 749.98, 'completed'),
            (1, '2024-09-01', 89.99, 'completed'),
            (2, '2024-09-10', 289.98, 'completed'),
            (3, '2024-09-20', 49.99, 'refunded'),
            (4, '2024-10-05', 1299.99, 'completed'),
            (5, '2024-10-15', 339.98, 'completed'),
            (1, '2024-11-01', 499.99, 'pending'),
            (6, '2024-11-10', 100.00, 'completed'),
            (2, '2025-01-05', 179.98, 'completed'),
            (3, '2025-01-15', 89.99, 'pending');

        INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
            (1, 1, 1, 1299.99), (1, 2, 1, 29.99), (1, 3, 1, 49.99),
            (2, 2, 2, 29.99), (2, 3, 1, 49.99), (2, 4, 1, 89.99),
            (3, 5, 1, 399.99), (3, 7, 1, 249.99),
            (4, 2, 1, 29.99),
            (5, 8, 1, 499.99), (5, 7, 1, 249.99),
            (6, 4, 1, 89.99),
            (7, 7, 1, 249.99), (7, 9, 1, 39.99),
            (8, 3, 1, 49.99),
            (9, 1, 1, 1299.99),
            (10, 5, 1, 399.99),
            (11, 8, 1, 499.99),
            (12, 10, 5, 12.99), (12, 11, 5, 8.99),
            (13, 2, 2, 29.99), (13, 3, 2, 49.99), (13, 4, 1, 89.99),
            (14, 4, 1, 89.99);
        """
    )

    conn.commit()
    conn.close()

    print(f"Sample database created: {db_path}")
    print("\nTables created:")
    print("  - products (12 items, 2 inactive)")
    print("  - customers (8 users, 1 test)")
    print("  - orders (14 orders, various statuses)")
    print("  - order_items (order details)")
    print("\nSample queries to try:")
    print("  - What is the total sales of active products in Q3 2024?")
    print("  - Show me the top 5 customers by order amount")
    print("  - Count products by category")


if __name__ == "__main__":
    create_sample_database()
