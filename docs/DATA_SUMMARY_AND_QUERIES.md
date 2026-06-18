# Data Sources Summary & Example Queries

## Overview

This system has two distinct data backends:
- **S3** (JSON + CSV files) — Sales financials and product inventory
- **Redshift** (SQL tables) — Workforce/HR, Customer Support, and Marketing Campaigns

The domains are intentionally non-overlapping so the routing layer can cleanly distinguish which backend to query.

---

## S3 Data Sources

### 1. `financial_data.json` (spoke-agent-json)

**Domain:** Sales Finance  
**Description:** Quarterly sales revenue and order volume broken down by product category and region.

| Column | Type | Description |
|--------|------|-------------|
| quarter | string | Quarter label (e.g., "Q1 2024") |
| region | string | North America, Europe |
| category | string | Electronics, Office Furniture, Office Supplies |
| revenue | number | Total revenue in USD |
| orders | number | Number of orders |
| avg_order_value | number | Average order value in USD |
| return_rate | number | Fraction of orders returned (0.0–1.0) |

**Coverage:** Q1 2024 – Q4 2024, 24 rows (4 quarters × 2 regions × 3 categories)

---

### 2. `product_catalog.csv` (spoke-agent-csv)

**Domain:** Product Inventory  
**Description:** Complete listing of products with pricing, stock levels, and supplier information.

| Column | Type | Description |
|--------|------|-------------|
| product_id | string | Unique product identifier (PROD-001, etc.) |
| name | string | Product name |
| category | string | Electronics, Office Furniture, Office Supplies |
| subcategory | string | Input Devices, Audio, Ergonomics, etc. |
| unit_price | number | Selling price in USD |
| stock_quantity | number | Current stock on hand |
| unit_cost | number | Cost per unit in USD |
| supplier | string | Supplier company name |
| supplier_region | string | North America, Europe |
| last_restocked | date | Last restock date |
| weight_kg | number | Product weight in kilograms |
| is_active | boolean | Whether the product is currently active |

**Coverage:** 30 products across 5 suppliers and 2 regions

---

## Redshift Data Sources (redshift-spoke-agent)

### 3. `workforce_metrics` table

**Domain:** HR / Workforce  
**Description:** Employee workforce data including salary, utilization, training, and engagement scores by department and office location.

| Column | Type | Description |
|--------|------|-------------|
| employee_id | VARCHAR | Unique employee ID (EMP-00001, etc.) |
| employee_name | VARCHAR | Full name |
| department | VARCHAR | Engineering, Product, Design, Data Science, DevOps, QA, Security |
| job_level | VARCHAR | Junior, Mid, Senior, Staff, Principal, Lead, Director |
| hire_date | DATE | Date of hire |
| office_location | VARCHAR | San Francisco, New York, London, Berlin, Toronto, Sydney |
| base_salary | DECIMAL | Annual base salary in USD |
| bonus_pct | DECIMAL | Bonus percentage (5–30%) |
| utilization_rate | DECIMAL | Work utilization rate (55–98%) |
| training_hours | INTEGER | Training hours completed |
| certifications | INTEGER | Number of certifications held |
| engagement_score | DECIMAL | Employee engagement score (2.5–5.0) |
| is_remote | BOOLEAN | Whether the employee works remotely |

**Coverage:** 120 employees across 7 departments and 6 office locations

---

### 4. `support_tickets` table

**Domain:** Customer Support  
**Description:** Customer support ticket data with resolution times, satisfaction ratings, escalation tracking, and first-contact resolution metrics.

| Column | Type | Description |
|--------|------|-------------|
| ticket_id | VARCHAR | Unique ticket ID (TKT-000001, etc.) |
| created_date | DATE | Ticket creation date |
| resolved_date | DATE | Resolution date (NULL if unresolved) |
| customer_tier | VARCHAR | Free, Starter, Professional, Enterprise, Strategic |
| channel | VARCHAR | Email, Chat, Phone, Self-Service Portal, Social Media |
| priority | VARCHAR | Low, Medium, High, Critical |
| issue_category | VARCHAR | Login/Auth, Billing, Feature Request, Performance, etc. |
| assigned_team | VARCHAR | Tier 1/2/3 Support, Billing Team, Account Management |
| resolution_hours | DECIMAL | Hours to resolution (NULL if unresolved) |
| satisfaction_rating | INTEGER | 1–5 rating (NULL if unresolved) |
| escalated | BOOLEAN | Whether the ticket was escalated |
| first_contact_resolution | BOOLEAN | Resolved on first contact |

**Coverage:** 200 tickets across 5 customer tiers, 5 channels, 10 issue categories

---

### 5. `marketing_campaigns` table

**Domain:** Marketing  
**Description:** Marketing campaign performance data with budget, spend, impressions, clicks, conversions, and attributed revenue.

| Column | Type | Description |
|--------|------|-------------|
| campaign_id | VARCHAR | Unique campaign ID (CAMP-0001, etc.) |
| campaign_name | VARCHAR | Campaign name |
| launch_date | DATE | Campaign start date |
| end_date | DATE | Campaign end date |
| channel | VARCHAR | Paid Search, Social Media, Email Newsletter, Content Marketing, Webinar, Partner Referral |
| target_audience | VARCHAR | Developers, CTOs/VPs, Small Business Owners, Enterprise Buyers, Startup Founders, Data Teams |
| budget | DECIMAL | Allocated budget in USD |
| spend | DECIMAL | Actual spend in USD |
| impressions | INTEGER | Total ad impressions |
| clicks | INTEGER | Total clicks |
| conversions | INTEGER | Total conversions |
| revenue_attributed | DECIMAL | Revenue attributed to campaign in USD |
| status | VARCHAR | Active, Completed, Paused |

**Coverage:** 80 campaigns across 6 channels and 6 audience segments

---

## Example Queries the System Should Accept

### S3 — Financial Data (JSON)

1. "What was the total revenue in Q4 2024?"
2. "Show me sales by region"
3. "Compare revenue between North America and Europe"
4. "Which category had the highest return rate in Q2 2024?"
5. "Show me quarterly revenue trends for Electronics"
6. "What is the average order value across all categories?"
7. "Which quarter had the most orders in North America?"
8. "Show return rates by category for Europe"
9. "What was the total revenue for Office Furniture in 2024?"
10. "Compare Q1 vs Q4 performance for all categories"

### S3 — Product Catalog (CSV)

11. "Show me all products in the Electronics category"
12. "Which products have stock below 50 units?"
13. "List products supplied by TechSupply Co"
14. "What is the average profit margin by category?"
15. "Show me the most expensive products"
16. "Which supplier region has the most products?"
17. "List all active products with their prices"
18. "What products were restocked in January 2025?"
19. "Show products sorted by stock quantity"
20. "What is the total inventory value (stock × unit_cost)?"

### Redshift — Workforce Metrics

21. "What is the average salary by department?"
22. "Show me workforce utilization rates by office location"
23. "How many employees are remote vs in-office?"
24. "What is the average engagement score by department?"
25. "Which department has the most certifications?"
26. "Show training hours by job level"
27. "What is the salary distribution for Senior engineers?"
28. "How many employees were hired in 2024?"
29. "Compare average bonus percentage across departments"
30. "Show me the headcount by office location"

### Redshift — Support Tickets

31. "What is the average resolution time by priority?"
32. "Show me ticket volume by customer tier"
33. "What percentage of tickets are escalated?"
34. "Which issue category has the most tickets?"
35. "What is the average satisfaction rating by channel?"
36. "Show me unresolved tickets by priority"
37. "What is the first-contact resolution rate by team?"
38. "How many critical tickets were created in 2024?"
39. "Compare resolution times between Enterprise and Free tier"
40. "Show ticket distribution by support channel"

### Redshift — Marketing Campaigns

41. "What is the total marketing spend by channel?"
42. "Show me campaign ROI (revenue_attributed / spend)"
43. "Which target audience has the highest conversion rate?"
44. "What is the average cost per click by channel?"
45. "Show me active campaigns and their budgets"
46. "Which channel drives the most conversions?"
47. "What is the total impressions by target audience?"
48. "Compare budget vs actual spend across campaigns"
49. "Show me the top 5 campaigns by attributed revenue"
50. "What is the click-through rate by marketing channel?"
