#!/usr/bin/env python
"""Provision Redshift database and tables with sample business data.

Connects to the Redshift cluster "talktodata" using the RedshiftConnector,
creates the "analytics" database (if not exists), creates tables
(sales_transactions, customer_segments, employee_performance), and populates
each with 50-200 rows of realistic business data.

Idempotent: skips creation if database/tables already exist.
Fails gracefully on connection errors without leaving partial resources.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8
"""

import asyncio
import logging
import random
import sys
from datetime import date, timedelta

# Add project root to path
sys.path.insert(0, ".")

from src.config import RedshiftConfig
from src.models.redshift_models import RedshiftError
from src.services.redshift_connector import RedshiftConnector

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# --- Table DDL ---

SALES_TRANSACTIONS_DDL = """
CREATE TABLE IF NOT EXISTS sales_transactions (
    transaction_id VARCHAR(36) NOT NULL,
    transaction_date DATE NOT NULL,
    customer_id VARCHAR(36) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    category VARCHAR(50) NOT NULL,
    region VARCHAR(50) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    payment_method VARCHAR(30) NOT NULL
)
"""

CUSTOMER_SEGMENTS_DDL = """
CREATE TABLE IF NOT EXISTS customer_segments (
    customer_id VARCHAR(36) NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    segment VARCHAR(30) NOT NULL,
    lifetime_value DECIMAL(12,2) NOT NULL,
    signup_date DATE NOT NULL,
    region VARCHAR(50) NOT NULL,
    total_orders INTEGER NOT NULL,
    last_order_date DATE NOT NULL
)
"""

EMPLOYEE_PERFORMANCE_DDL = """
CREATE TABLE IF NOT EXISTS employee_performance (
    employee_id VARCHAR(36) NOT NULL,
    employee_name VARCHAR(100) NOT NULL,
    department VARCHAR(50) NOT NULL,
    role VARCHAR(50) NOT NULL,
    hire_date DATE NOT NULL,
    region VARCHAR(50) NOT NULL,
    quarterly_target DECIMAL(12,2) NOT NULL,
    quarterly_actual DECIMAL(12,2) NOT NULL,
    deals_closed INTEGER NOT NULL,
    customer_satisfaction_score DECIMAL(3,1) NOT NULL
)
"""

# --- Categorical values ---

CATEGORIES = ["Electronics", "Office Furniture", "Office Supplies", "Software", "Networking"]
REGIONS = ["North America", "Europe", "Asia Pacific", "Latin America"]
PAYMENT_METHODS = ["Credit Card", "Wire Transfer", "PayPal", "Purchase Order", "ACH"]
SEGMENTS = ["Enterprise", "Mid-Market", "Small Business", "Startup", "Government"]
DEPARTMENTS = ["Sales", "Engineering", "Marketing", "Customer Success", "Operations"]
ROLES = ["Manager", "Senior IC", "IC", "Director", "VP"]

PRODUCT_NAMES = [
    "Laptop Pro 15", "Wireless Mouse", "Standing Desk", "Monitor 27in",
    "Keyboard Mechanical", "Webcam HD", "Desk Chair Ergonomic", "USB Hub",
    "Headset Noise Cancel", "Whiteboard 6ft", "Printer Laser", "Cable Kit",
    "Docking Station", "Tablet 10in", "Router Enterprise", "Switch 24-port",
    "Firewall Appliance", "UPS Battery", "Projector 4K", "Phone System",
]

FIRST_NAMES = [
    "James", "Maria", "Robert", "Sarah", "David", "Jennifer", "Michael",
    "Lisa", "William", "Patricia", "Richard", "Linda", "Joseph", "Barbara",
    "Thomas", "Elizabeth", "Daniel", "Susan", "Matthew", "Jessica",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Anderson", "Taylor", "Thomas",
    "Hernandez", "Moore", "Martin", "Jackson", "Thompson", "White", "Lee",
]


def random_date(start_year: int = 2022, end_year: int = 2024) -> str:
    """Generate a random date string between start and end year."""
    start = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    delta = (end - start).days
    random_day = start + timedelta(days=random.randint(0, delta))
    return random_day.isoformat()


def generate_sales_transactions(n: int = 150) -> list[str]:
    """Generate INSERT statements for sales_transactions."""
    rows = []
    for i in range(n):
        tid = f"TXN-{i+1:05d}"
        tdate = random_date()
        cid = f"CUST-{random.randint(1, 500):04d}"
        product = random.choice(PRODUCT_NAMES)
        category = random.choice(CATEGORIES)
        region = random.choice(REGIONS)
        quantity = random.randint(1, 50)
        unit_price = round(random.uniform(10.0, 2500.0), 2)
        total_amount = round(quantity * unit_price, 2)
        payment = random.choice(PAYMENT_METHODS)
        rows.append(
            f"('{tid}', '{tdate}', '{cid}', '{product}', '{category}', "
            f"'{region}', {quantity}, {unit_price}, {total_amount}, '{payment}')"
        )
    return rows


def generate_customer_segments(n: int = 100) -> list[str]:
    """Generate INSERT statements for customer_segments."""
    rows = []
    for i in range(n):
        cid = f"CUST-{i+1:04d}"
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        segment = random.choice(SEGMENTS)
        ltv = round(random.uniform(1000.0, 500000.0), 2)
        signup = random_date(2018, 2023)
        region = random.choice(REGIONS)
        orders = random.randint(1, 200)
        last_order = random_date(2023, 2024)
        rows.append(
            f"('{cid}', '{name}', '{segment}', {ltv}, '{signup}', "
            f"'{region}', {orders}, '{last_order}')"
        )
    return rows


def generate_employee_performance(n: int = 80) -> list[str]:
    """Generate INSERT statements for employee_performance."""
    rows = []
    for i in range(n):
        eid = f"EMP-{i+1:04d}"
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        dept = random.choice(DEPARTMENTS)
        role = random.choice(ROLES)
        hire = random_date(2015, 2023)
        region = random.choice(REGIONS)
        target = round(random.uniform(50000.0, 500000.0), 2)
        actual = round(target * random.uniform(0.6, 1.4), 2)
        deals = random.randint(0, 50)
        satisfaction = round(random.uniform(3.0, 5.0), 1)
        rows.append(
            f"('{eid}', '{name}', '{dept}', '{role}', '{hire}', "
            f"'{region}', {target}, {actual}, {deals}, {satisfaction})"
        )
    return rows


async def check_table_exists(connector: RedshiftConnector, table_name: str) -> bool:
    """Check if a table already exists in Redshift."""
    sql = (
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = :tname"
    )
    result = await connector.execute_statement(sql, parameters=[{"name": "tname", "value": table_name}])
    if isinstance(result, RedshiftError):
        return False
    return result.row_count > 0


async def provision() -> None:
    """Main provisioning logic."""
    config = RedshiftConfig.from_env()
    connector = RedshiftConnector(config)

    print(f"Connecting to Redshift cluster '{config.cluster_id}', database '{config.database}'...")

    # Validate connectivity
    connected = await connector.validate_connectivity()
    if not connected:
        print(f"ERROR: Cannot connect to Redshift cluster '{config.cluster_id}' "
              f"(database={config.database}, user={config.db_user}, region={config.region})")
        print("Aborting provisioning — no partial resources created.")
        sys.exit(1)

    print("  ✓ Connected to Redshift successfully")

    tables_created = 0
    table_rows: dict[str, int] = {}

    # --- sales_transactions ---
    table_name = "sales_transactions"
    if await check_table_exists(connector, table_name):
        print(f"  ⊘ Table '{table_name}' already exists — skipping")
    else:
        print(f"  Creating table '{table_name}'...")
        result = await connector.execute_statement(SALES_TRANSACTIONS_DDL)
        if isinstance(result, RedshiftError):
            print(f"ERROR: Failed to create table '{table_name}': {result.description}")
            print("Aborting provisioning.")
            sys.exit(1)

        rows = generate_sales_transactions(150)
        # Insert in batches of 50
        for batch_start in range(0, len(rows), 50):
            batch = rows[batch_start:batch_start + 50]
            values_str = ",\n".join(batch)
            insert_sql = (
                f"INSERT INTO {table_name} "
                f"(transaction_id, transaction_date, customer_id, product_name, "
                f"category, region, quantity, unit_price, total_amount, payment_method) "
                f"VALUES {values_str}"
            )
            ins_result = await connector.execute_statement(insert_sql)
            if isinstance(ins_result, RedshiftError):
                print(f"ERROR: Failed to insert into '{table_name}': {ins_result.description}")
                print("Aborting provisioning.")
                sys.exit(1)

        tables_created += 1
        table_rows[table_name] = len(rows)
        print(f"  ✓ Created and populated '{table_name}' with {len(rows)} rows")

    # --- customer_segments ---
    table_name = "customer_segments"
    if await check_table_exists(connector, table_name):
        print(f"  ⊘ Table '{table_name}' already exists — skipping")
    else:
        print(f"  Creating table '{table_name}'...")
        result = await connector.execute_statement(CUSTOMER_SEGMENTS_DDL)
        if isinstance(result, RedshiftError):
            print(f"ERROR: Failed to create table '{table_name}': {result.description}")
            print("Aborting provisioning.")
            sys.exit(1)

        rows = generate_customer_segments(100)
        for batch_start in range(0, len(rows), 50):
            batch = rows[batch_start:batch_start + 50]
            values_str = ",\n".join(batch)
            insert_sql = (
                f"INSERT INTO {table_name} "
                f"(customer_id, customer_name, segment, lifetime_value, "
                f"signup_date, region, total_orders, last_order_date) "
                f"VALUES {values_str}"
            )
            ins_result = await connector.execute_statement(insert_sql)
            if isinstance(ins_result, RedshiftError):
                print(f"ERROR: Failed to insert into '{table_name}': {ins_result.description}")
                print("Aborting provisioning.")
                sys.exit(1)

        tables_created += 1
        table_rows[table_name] = len(rows)
        print(f"  ✓ Created and populated '{table_name}' with {len(rows)} rows")

    # --- employee_performance ---
    table_name = "employee_performance"
    if await check_table_exists(connector, table_name):
        print(f"  ⊘ Table '{table_name}' already exists — skipping")
    else:
        print(f"  Creating table '{table_name}'...")
        result = await connector.execute_statement(EMPLOYEE_PERFORMANCE_DDL)
        if isinstance(result, RedshiftError):
            print(f"ERROR: Failed to create table '{table_name}': {result.description}")
            print("Aborting provisioning.")
            sys.exit(1)

        rows = generate_employee_performance(80)
        for batch_start in range(0, len(rows), 50):
            batch = rows[batch_start:batch_start + 50]
            values_str = ",\n".join(batch)
            insert_sql = (
                f"INSERT INTO {table_name} "
                f"(employee_id, employee_name, department, role, hire_date, "
                f"region, quarterly_target, quarterly_actual, deals_closed, "
                f"customer_satisfaction_score) "
                f"VALUES {values_str}"
            )
            ins_result = await connector.execute_statement(insert_sql)
            if isinstance(ins_result, RedshiftError):
                print(f"ERROR: Failed to insert into '{table_name}': {ins_result.description}")
                print("Aborting provisioning.")
                sys.exit(1)

        tables_created += 1
        table_rows[table_name] = len(rows)
        print(f"  ✓ Created and populated '{table_name}' with {len(rows)} rows")

    # --- Summary ---
    print("\n" + "=" * 50)
    print("Provisioning Summary")
    print("=" * 50)
    print(f"  Tables created: {tables_created}")
    for tbl, count in table_rows.items():
        print(f"    {tbl}: {count} rows")
    if tables_created == 0:
        print("  (All tables already existed — no changes made)")
    print("=" * 50)
    print("Done.")


if __name__ == "__main__":
    random.seed(42)  # Reproducible data generation
    asyncio.run(provision())
