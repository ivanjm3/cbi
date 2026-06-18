#!/usr/bin/env python
"""Provision Redshift database and tables with sample business data.

Connects to the Redshift cluster "talktodata" using the RedshiftConnector,
creates the "analytics" database (if not exists), creates tables
(workforce_metrics, support_tickets, marketing_campaigns), and populates
each with 50-200 rows of realistic business data.

These tables cover HR/Workforce, Customer Support, and Marketing domains —
complementary to but distinct from the S3-based sales/inventory data.

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

# Parse CLI args
FORCE_RECREATE = "--force" in sys.argv or "--recreate" in sys.argv

# --- Table DDL ---

WORKFORCE_METRICS_DDL = """
CREATE TABLE IF NOT EXISTS workforce_metrics (
    employee_id VARCHAR(36) NOT NULL,
    employee_name VARCHAR(100) NOT NULL,
    department VARCHAR(50) NOT NULL,
    job_level VARCHAR(30) NOT NULL,
    hire_date DATE NOT NULL,
    office_location VARCHAR(50) NOT NULL,
    base_salary DECIMAL(10,2) NOT NULL,
    bonus_pct DECIMAL(5,2) NOT NULL,
    utilization_rate DECIMAL(5,2) NOT NULL,
    training_hours INTEGER NOT NULL,
    certifications INTEGER NOT NULL,
    engagement_score DECIMAL(3,1) NOT NULL,
    is_remote BOOLEAN NOT NULL
)
"""

SUPPORT_TICKETS_DDL = """
CREATE TABLE IF NOT EXISTS support_tickets (
    ticket_id VARCHAR(36) NOT NULL,
    created_date DATE NOT NULL,
    resolved_date DATE,
    customer_tier VARCHAR(30) NOT NULL,
    channel VARCHAR(30) NOT NULL,
    priority VARCHAR(20) NOT NULL,
    issue_category VARCHAR(50) NOT NULL,
    assigned_team VARCHAR(50) NOT NULL,
    resolution_hours DECIMAL(8,2),
    satisfaction_rating INTEGER,
    escalated BOOLEAN NOT NULL,
    first_contact_resolution BOOLEAN NOT NULL
)
"""

MARKETING_CAMPAIGNS_DDL = """
CREATE TABLE IF NOT EXISTS marketing_campaigns (
    campaign_id VARCHAR(36) NOT NULL,
    campaign_name VARCHAR(200) NOT NULL,
    launch_date DATE NOT NULL,
    end_date DATE NOT NULL,
    channel VARCHAR(50) NOT NULL,
    target_audience VARCHAR(50) NOT NULL,
    budget DECIMAL(12,2) NOT NULL,
    spend DECIMAL(12,2) NOT NULL,
    impressions INTEGER NOT NULL,
    clicks INTEGER NOT NULL,
    conversions INTEGER NOT NULL,
    revenue_attributed DECIMAL(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL
)
"""

# --- Categorical values ---

DEPARTMENTS = ["Engineering", "Product", "Design", "Data Science", "DevOps", "QA", "Security"]
JOB_LEVELS = ["Junior", "Mid", "Senior", "Staff", "Principal", "Lead", "Director"]
OFFICE_LOCATIONS = ["San Francisco", "New York", "London", "Berlin", "Toronto", "Sydney"]

CUSTOMER_TIERS = ["Free", "Starter", "Professional", "Enterprise", "Strategic"]
SUPPORT_CHANNELS = ["Email", "Chat", "Phone", "Self-Service Portal", "Social Media"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]
ISSUE_CATEGORIES = [
    "Login/Authentication", "Billing Dispute", "Feature Request",
    "Performance Issue", "Data Export", "Integration Error",
    "Account Management", "API Failure", "Onboarding Help", "Downtime Report",
]
SUPPORT_TEAMS = ["Tier 1 Support", "Tier 2 Support", "Tier 3 Engineering", "Billing Team", "Account Management"]

MARKETING_CHANNELS = ["Paid Search", "Social Media", "Email Newsletter", "Content Marketing", "Webinar", "Partner Referral"]
TARGET_AUDIENCES = ["Developers", "CTOs/VPs", "Small Business Owners", "Enterprise Buyers", "Startup Founders", "Data Teams"]
CAMPAIGN_STATUSES = ["Active", "Completed", "Paused"]

CAMPAIGN_NAME_PREFIXES = [
    "Spring Launch", "Q1 Blitz", "Developer Summit", "Cloud Migration",
    "AI Revolution", "Scale Up", "Data Unlock", "Platform Shift",
    "Growth Accelerator", "Innovation Week", "Winter Push", "Year-End Drive",
    "Startup Special", "Enterprise Focus", "Partner Power", "Retention Boost",
]

FIRST_NAMES = [
    "Aisha", "Carlos", "Priya", "Oluwaseun", "Yuki", "Mikhail",
    "Fatima", "Henrik", "Mei", "Sergei", "Amara", "Chen",
    "Ingrid", "Dmitri", "Nalini", "Kwame", "Anya", "Lars",
    "Chioma", "Kenji",
]

LAST_NAMES = [
    "Nakamura", "Okafor", "Petrov", "Singh", "Johansson", "Al-Rashid",
    "Kim", "Fernandez", "Okonkwo", "Andersen", "Patel", "Muller",
    "Takahashi", "Adeyemi", "Bergstrom", "Chakraborty", "Ivanova", "Park",
    "Osei", "Lindqvist",
]


def random_date(start_year: int = 2022, end_year: int = 2024) -> str:
    """Generate a random date string between start and end year."""
    start = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    delta = (end - start).days
    random_day = start + timedelta(days=random.randint(0, delta))
    return random_day.isoformat()


def generate_workforce_metrics(n: int = 120) -> list[str]:
    """Generate INSERT statements for workforce_metrics."""
    rows = []
    for i in range(n):
        eid = f"EMP-{i+1:05d}"
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        dept = random.choice(DEPARTMENTS)
        level = random.choice(JOB_LEVELS)
        hire = random_date(2016, 2024)
        location = random.choice(OFFICE_LOCATIONS)
        salary = round(random.uniform(65000.0, 220000.0), 2)
        bonus = round(random.uniform(5.0, 30.0), 2)
        utilization = round(random.uniform(55.0, 98.0), 2)
        training = random.randint(0, 80)
        certs = random.randint(0, 8)
        engagement = round(random.uniform(2.5, 5.0), 1)
        is_remote = random.choice(["true", "false"])
        rows.append(
            f"('{eid}', '{name}', '{dept}', '{level}', '{hire}', "
            f"'{location}', {salary}, {bonus}, {utilization}, {training}, "
            f"{certs}, {engagement}, {is_remote})"
        )
    return rows


def generate_support_tickets(n: int = 200) -> list[str]:
    """Generate INSERT statements for support_tickets."""
    rows = []
    for i in range(n):
        tid = f"TKT-{i+1:06d}"
        created = random_date(2023, 2024)
        # Some tickets unresolved
        if random.random() < 0.15:
            resolved = "NULL"
            resolution_hours = "NULL"
            satisfaction = "NULL"
        else:
            days_to_resolve = random.randint(0, 14)
            resolved_date = date.fromisoformat(created) + timedelta(days=days_to_resolve)
            resolved = f"'{resolved_date.isoformat()}'"
            resolution_hours = round(random.uniform(0.5, 336.0), 2)
            satisfaction = random.randint(1, 5)
        tier = random.choice(CUSTOMER_TIERS)
        channel = random.choice(SUPPORT_CHANNELS)
        priority = random.choice(PRIORITIES)
        category = random.choice(ISSUE_CATEGORIES)
        team = random.choice(SUPPORT_TEAMS)
        escalated = random.choice(["true", "false"])
        fcr = random.choice(["true", "false"])
        rows.append(
            f"('{tid}', '{created}', {resolved}, '{tier}', '{channel}', "
            f"'{priority}', '{category}', '{team}', {resolution_hours}, "
            f"{satisfaction}, {escalated}, {fcr})"
        )
    return rows


def generate_marketing_campaigns(n: int = 80) -> list[str]:
    """Generate INSERT statements for marketing_campaigns."""
    rows = []
    for i in range(n):
        cid = f"CAMP-{i+1:04d}"
        name = f"{random.choice(CAMPAIGN_NAME_PREFIXES)} - {random.choice(MARKETING_CHANNELS)}"
        launch = random_date(2023, 2024)
        launch_d = date.fromisoformat(launch)
        duration = random.randint(7, 90)
        end_d = launch_d + timedelta(days=duration)
        end = end_d.isoformat()
        channel = random.choice(MARKETING_CHANNELS)
        audience = random.choice(TARGET_AUDIENCES)
        budget = round(random.uniform(5000.0, 150000.0), 2)
        spend = round(budget * random.uniform(0.4, 1.0), 2)
        impressions = random.randint(10000, 2000000)
        clicks = random.randint(int(impressions * 0.005), int(impressions * 0.08))
        conversions = random.randint(int(clicks * 0.01), int(clicks * 0.15))
        revenue = round(conversions * random.uniform(50.0, 500.0), 2)
        status = random.choice(CAMPAIGN_STATUSES)
        rows.append(
            f"('{cid}', '{name}', '{launch}', '{end}', '{channel}', "
            f"'{audience}', {budget}, {spend}, {impressions}, {clicks}, "
            f"{conversions}, {revenue}, '{status}')"
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


async def drop_table(connector: RedshiftConnector, table_name: str) -> bool:
    """Drop a table if it exists. Returns True on success."""
    result = await connector.execute_statement(f"DROP TABLE IF EXISTS {table_name}")
    if isinstance(result, RedshiftError):
        print(f"  WARNING: Failed to drop '{table_name}': {result.description}")
        return False
    print(f"  ✓ Dropped table '{table_name}'")
    return True


async def provision() -> None:
    """Main provisioning logic."""
    config = RedshiftConfig.from_env()
    connector = RedshiftConnector(config)

    print(f"Connecting to Redshift cluster '{config.cluster_id}', database '{config.database}'...")
    if FORCE_RECREATE:
        print("  (--force mode: will drop and recreate all tables)")

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

    # --- workforce_metrics ---
    table_name = "workforce_metrics"
    if FORCE_RECREATE:
        await drop_table(connector, table_name)
    if not FORCE_RECREATE and await check_table_exists(connector, table_name):
        print(f"  ⊘ Table '{table_name}' already exists — skipping")
    else:
        print(f"  Creating table '{table_name}'...")
        result = await connector.execute_statement(WORKFORCE_METRICS_DDL)
        if isinstance(result, RedshiftError):
            print(f"ERROR: Failed to create table '{table_name}': {result.description}")
            print("Aborting provisioning.")
            sys.exit(1)

        rows = generate_workforce_metrics(120)
        # Insert in batches of 50
        for batch_start in range(0, len(rows), 50):
            batch = rows[batch_start:batch_start + 50]
            values_str = ",\n".join(batch)
            insert_sql = (
                f"INSERT INTO {table_name} "
                f"(employee_id, employee_name, department, job_level, hire_date, "
                f"office_location, base_salary, bonus_pct, utilization_rate, "
                f"training_hours, certifications, engagement_score, is_remote) "
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

    # --- support_tickets ---
    table_name = "support_tickets"
    if FORCE_RECREATE:
        await drop_table(connector, table_name)
    if not FORCE_RECREATE and await check_table_exists(connector, table_name):
        print(f"  ⊘ Table '{table_name}' already exists — skipping")
    else:
        print(f"  Creating table '{table_name}'...")
        result = await connector.execute_statement(SUPPORT_TICKETS_DDL)
        if isinstance(result, RedshiftError):
            print(f"ERROR: Failed to create table '{table_name}': {result.description}")
            print("Aborting provisioning.")
            sys.exit(1)

        rows = generate_support_tickets(200)
        for batch_start in range(0, len(rows), 50):
            batch = rows[batch_start:batch_start + 50]
            values_str = ",\n".join(batch)
            insert_sql = (
                f"INSERT INTO {table_name} "
                f"(ticket_id, created_date, resolved_date, customer_tier, "
                f"channel, priority, issue_category, assigned_team, "
                f"resolution_hours, satisfaction_rating, escalated, first_contact_resolution) "
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

    # --- marketing_campaigns ---
    table_name = "marketing_campaigns"
    if FORCE_RECREATE:
        await drop_table(connector, table_name)
    if not FORCE_RECREATE and await check_table_exists(connector, table_name):
        print(f"  ⊘ Table '{table_name}' already exists — skipping")
    else:
        print(f"  Creating table '{table_name}'...")
        result = await connector.execute_statement(MARKETING_CAMPAIGNS_DDL)
        if isinstance(result, RedshiftError):
            print(f"ERROR: Failed to create table '{table_name}': {result.description}")
            print("Aborting provisioning.")
            sys.exit(1)

        rows = generate_marketing_campaigns(80)
        for batch_start in range(0, len(rows), 50):
            batch = rows[batch_start:batch_start + 50]
            values_str = ",\n".join(batch)
            insert_sql = (
                f"INSERT INTO {table_name} "
                f"(campaign_id, campaign_name, launch_date, end_date, channel, "
                f"target_audience, budget, spend, impressions, clicks, "
                f"conversions, revenue_attributed, status) "
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
