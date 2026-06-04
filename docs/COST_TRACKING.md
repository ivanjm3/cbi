# Cost Tracking

The system automatically tracks all Bedrock API calls and their costs.

## How It Works

Every Bedrock invocation (NLP classification, orchestrator routing, spoke agent queries, visualization generation) is logged to a local SQLite database (`data/cost_tracker.db`) with:

- Timestamp
- Model ID
- Component (which service made the call)
- Input/output token counts
- Estimated cost in USD
- Correlation ID (for request tracing)

## Viewing Cost Reports

Use the `cost_report.py` script:

```bash
# Today's costs
python scripts/cost_report.py today

# Specific date
python scripts/cost_report.py daily 2026-06-04

# Monthly summary
python scripts/cost_report.py monthly 2026 6

# All-time totals
python scripts/cost_report.py all
```

## Example Output

```
======================================================================
BEDROCK COST REPORT — 2026-06-04
======================================================================
Total Calls:         47
Total Cost:          $0.0521
Input Tokens:        12,450
Output Tokens:       3,872

Breakdown by Component:
----------------------------------------------------------------------
Component                            Calls            Cost          Tokens
----------------------------------------------------------------------
orchestrator_hub                        12          $0.0198          4,122
spoke_agent_json                        10          $0.0145          3,654
spoke_agent_csv                         10          $0.0132          3,298
visualization_renderer                   8          $0.0031          1,987
nlp_translator                           7          $0.0015          1,261
======================================================================
```

## Current Pricing (as of June 2026)

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|-----------------------|------------------------|
| Claude Haiku | $0.25 | $1.25 |
| Claude Sonnet | $3.00 | $15.00 |
| Titan Embeddings | $0.10 | N/A |

**Note:** Strands SDK doesn't expose exact token counts, so agent invocations use estimated counts based on response length. The NLP translator (boto3 direct) has exact counts.

## Setting AWS Budgets

To prevent runaway costs:

1. AWS Console → Billing → Budgets → Create budget
2. Set monthly budget (e.g., $10)
3. Filter to service: "Amazon Bedrock"
4. Set alerts at 50%, 80%, 100%
5. Add email/SNS notifications

## Database Location

`data/cost_tracker.db` — SQLite database with all cost records. You can query it directly:

```bash
sqlite3 data/cost_tracker.db "SELECT * FROM bedrock_usage ORDER BY timestamp DESC LIMIT 10;"
```
