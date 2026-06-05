# Running Guide — Ontology NLP Query System

## Prerequisites

- Python 3.11+
- AWS CLI configured with profile `PowerUserAccess-654654478821`
- Access to Amazon Bedrock (Claude Haiku + Titan Embeddings V2)
- S3 bucket `visualization-poc-bucket` created

## Setup

```bash
# Create virtual environment
python -m venv .venv

# Activate (Linux/macOS)
source .venv/bin/activate

# Activate (Windows)
# .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Upload initial data to S3 (ontology, sample data files)
python scripts/setup_s3.py
```

## Starting the System

```bash
python run_all.py
```

This starts 5 services:
- NLP Translator → http://localhost:8001
- Orchestrator Hub → http://localhost:8002
- Guardrail Layer → http://localhost:8003
- Visualization Renderer → http://localhost:8004
- Spoke Agent → http://localhost:8010

Once you see "System Ready!", you can start submitting queries.

Press `Ctrl+C` to stop all services.

---

## Submitting Queries

All queries go to: `POST http://localhost:8001/query`

### Using curl

```bash
curl -X POST http://localhost:8001/query -H "Content-Type: application/json" -d "{\"query_text\": \"your question here\"}"
```

### Using PowerShell (Invoke-RestMethod)

```powershell
$body = @{ query_text = "your question here" } | ConvertTo-Json
Invoke-RestMethod -Method POST -Uri http://localhost:8001/query -ContentType "application/json" -Body $body
```

---

## Example Prompts

### Financial Data Queries (JSON source)

These target the financial dataset (quarterly revenue, order volume by category/region):

```bash
# Lookup — retrieve specific data
curl -X POST http://localhost:8001/query -H "Content-Type: application/json" -d "{\"query_text\": \"show me quarterly sales revenue\"}"

# Aggregation — compute totals/averages
curl -X POST http://localhost:8001/query -H "Content-Type: application/json" -d "{\"query_text\": \"what is the total revenue across all quarters\"}"

# Comparison — group and compare
curl -X POST http://localhost:8001/query -H "Content-Type: application/json" -d "{\"query_text\": \"compare revenue by region\"}"

# Time-based lookup
curl -X POST http://localhost:8001/query -H "Content-Type: application/json" -d "{\"query_text\": \"show quarterly report for Q1 and Q2\"}"
```

### Product Catalog Queries (CSV source)

These target the product catalog (names, categories, prices, stock, suppliers):

```bash
# Lookup — retrieve products
curl -X POST http://localhost:8001/query -H "Content-Type: application/json" -d "{\"query_text\": \"list all products in the catalog\"}"

# Aggregation — summarize product data
curl -X POST http://localhost:8001/query -H "Content-Type: application/json" -d "{\"query_text\": \"what is the average product price\"}"

# Comparison — compare categories
curl -X POST http://localhost:8001/query -H "Content-Type: application/json" -d "{\"query_text\": \"compare product counts by category\"}"

# Filtered lookup
curl -X POST http://localhost:8001/query -H "Content-Type: application/json" -d "{\"query_text\": \"show me employee count data\"}"
```

### Cross-Source Queries (Both JSON + CSV)

These may trigger both data source tools within the spoke agent:

```bash
# Mixed entities spanning financial + product
curl -X POST http://localhost:8001/query -H "Content-Type: application/json" -d "{\"query_text\": \"compare sales revenue against product catalog pricing\"}"

# Broad query that touches both domains
curl -X POST http://localhost:8001/query -H "Content-Type: application/json" -d "{\"query_text\": \"give me an overview of revenue and products\"}"
```

### Invalid / Edge Case Queries

These test error handling, guardrails, and ontology mismatch scenarios:

```bash
# No ontology match — should return NLPError with NO_ONTOLOGY_MATCH
curl -X POST http://localhost:8001/query -H "Content-Type: application/json" -d "{\"query_text\": \"what is the weather today\"}"

# Empty query — should return UNPARSEABLE_QUERY
curl -X POST http://localhost:8001/query -H "Content-Type: application/json" -d "{\"query_text\": \"\"}"

# Whitespace only — should return UNPARSEABLE_QUERY
curl -X POST http://localhost:8001/query -H "Content-Type: application/json" -d "{\"query_text\": \"   \"}"

# Gibberish — likely NO_ONTOLOGY_MATCH or AMBIGUOUS_INTENT
curl -X POST http://localhost:8001/query -H "Content-Type: application/json" -d "{\"query_text\": \"asdfghjkl zxcvbnm\"}"

# Very long query
curl -X POST http://localhost:8001/query -H "Content-Type: application/json" -d "{\"query_text\": \"I want to see a very detailed breakdown of all the quarterly sales revenue data broken down by every single region and every single product category with comparisons and aggregations and trends\"}"
```

### Guardrail Testing

These test content safety filtering (Bedrock Guardrails + local rules):

```bash
# PII in response (if data contained PII, it would be redacted)
# The guardrail checks OUTBOUND responses, not input queries

# Vulgar input — note: guardrails apply to agent OUTPUT, not input.
# But you can test if the system propagates inappropriate content:
curl -X POST http://localhost:8001/query -H "Content-Type: application/json" -d "{\"query_text\": \"show me the damn revenue numbers\"}"
```

---

## Checking Health

```bash
# Check all services
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
curl http://localhost:8004/health
curl http://localhost:8010/health
```

---

## Checking Incurred Costs

Every Bedrock API call (LLM inference + embeddings) is tracked and stored in S3.

### CLI Cost Report

```bash
# Today's cost breakdown
python scripts/cost_report.py today

# Specific date
python scripts/cost_report.py daily 2026-06-04

# Monthly summary
python scripts/cost_report.py monthly 2026 6

# All-time totals
python scripts/cost_report.py all
```

### Example Output

```
======================================================================
BEDROCK COST REPORT — 2026-06-04
======================================================================
Total Calls:         12
Total Cost:          $0.0087
Input Tokens:        3,450
Output Tokens:       1,203

Breakdown by Component:
----------------------------------------------------------------------
Component                            Calls            Cost          Tokens
----------------------------------------------------------------------
orchestrator_hub                         3          $0.0032          1,455
spoke_agent                              3          $0.0028          1,312
visualization_renderer                   3          $0.0018            998
nlp_translator                           3          $0.0009            888
======================================================================
```

### Direct S3 Query

Cost records are stored at `s3://visualization-poc-bucket/costs/{YYYY-MM-DD}/{uuid}.json`.

```bash
# List today's cost records
aws s3 ls s3://visualization-poc-bucket/costs/2026-06-04/ --profile PowerUserAccess-654654478821

# Download and view a specific record
aws s3 cp s3://visualization-poc-bucket/costs/2026-06-04/some-uuid.json - --profile PowerUserAccess-654654478821
```

Each record contains:
```json
{
  "id": "uuid",
  "timestamp": "2026-06-04T10:30:00Z",
  "model_id": "anthropic.claude-haiku-4-5-20251001-v1:0",
  "component": "orchestrator_hub",
  "input_tokens": 485,
  "output_tokens": 123,
  "cost_usd": 0.000275,
  "correlation_id": "request-uuid"
}
```

### Cost Per Query (Approximate)

A single query through the full pipeline makes approximately:
- 1 NLP classification call (Claude Haiku) — **only on first occurrence, cached after**
- 1 Input guardrail call (Bedrock Guardrails) — **only on first occurrence, cached after**
- 1 Output guardrail call (Bedrock Guardrails) — **only on first occurrence for same data, cached after**
- 1 Visualization rendering call (Claude Haiku via Strands) — **only on first occurrence for same data, cached after**
- 0 Spoke Agent LLM calls — **deterministic routing, no LLM**
- 0 Orchestrator LLM calls — **deterministic dispatch, no LLM**

At Claude Haiku pricing ($0.25/1M input, $1.25/1M output), a typical first query costs ~$0.001–$0.003. Repeat queries cost $0 (all cached).

**Latency profile:**
- First query: ~30-40s (dominated by visualization LLM agent)
- Repeat identical query: <1s (all caches hit)

---

## Troubleshooting

### "Cannot connect to Orchestrator Hub"
Services start in order. Wait a few seconds for all health checks to pass.

### "No ontology concepts matched the query"
The system only understands queries related to entities in the ontology (sales_revenue, quarterly_report, product_catalog, employee_count). Queries about unrelated topics will get NO_ONTOLOGY_MATCH.

### "Bedrock AccessDeniedException"
Verify model access is enabled:
```bash
aws bedrock get-foundation-model-availability --model-id anthropic.claude-haiku-4-5-20251001-v1:0 --profile PowerUserAccess-654654478821
```

### SSL Certificate errors
The system uses `verify=False` for S3 in setup_s3.py. For other services, you may need to set:
```bash
set AWS_CA_BUNDLE=path/to/cert.pem
```
Or add `verify=False` to boto3 client calls in `src/config.py`.

### Costs seem high
Check which component is making the most calls:
```bash
python scripts/cost_report.py today
```
The system is optimized to minimize LLM calls:
- Spoke Agent uses deterministic routing (no LLM)
- Orchestrator uses direct entity-ref dispatch (no LLM)
- NLP classification and visualization results are cached
- Only the visualization renderer uses an LLM agent (Strands), and results are cached per payload+query
