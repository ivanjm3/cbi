# Cost Tracking

The system automatically tracks all Bedrock API calls and their costs.

## How It Works

Every Bedrock invocation (NLP classification, orchestrator routing, spoke agent queries, visualization generation) is logged to S3 as individual JSON records organized by date:

```
s3://visualization-poc-bucket/costs/{YYYY-MM-DD}/{uuid}.json
```

Each record contains:
- Timestamp
- Model ID
- Component (which service made the call)
- Input/output token counts
- Estimated cost in USD
- Correlation ID (for request tracing)

**Accuracy note:** The NLP Translator uses direct Bedrock API calls and captures exact token counts from the response. Agent-based components (orchestrator_hub, spoke_agent, visualization_renderer) use Strands SDK which doesn't expose token counts directly — these use estimated counts based on response length.

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

## Direct S3 Query

```bash
# List today's cost records
aws s3 ls s3://visualization-poc-bucket/costs/2026-06-04/ --profile PowerUserAccess-654654478821

# Download and view a specific record
aws s3 cp s3://visualization-poc-bucket/costs/2026-06-04/some-uuid.json - --profile PowerUserAccess-654654478821
```

Each record looks like:
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

## Current Pricing (as of June 2026)

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|-----------------------|------------------------|
| Claude 3.5 Haiku | $0.80 | $4.00 |
| Claude Haiku 4.5 | $0.25 | $1.25 |
| Claude Sonnet 4 | $3.00 | $15.00 |
| Titan Embeddings V2 | $0.02 | N/A |
| Titan Embeddings V1 | $0.10 | N/A |

The default model is Claude 3.5 Haiku (`us.anthropic.claude-3-5-haiku-20241022-v1:0`).

## Cost Efficiency Features

- **Classification cache:** An in-memory LRU cache (1000 entries) prevents repeat Bedrock calls for identical query classifications.
- **Result cache:** The orchestrator caches responses by deterministic intent hash, avoiding redundant agent invocations for identical queries.
- **Fire-and-forget logging:** Cost record writes to S3 never block the request pipeline — failures are logged but swallowed.

## Scaling Considerations

At POC volume (tens to hundreds of queries/day), the current approach is efficient. Each report reads individual JSON files from S3 which is O(n) in the number of daily records. If volume grows significantly, consider:
- Aggregating into daily summary files
- Using S3 Select or Athena for querying
- Migrating to DynamoDB with date partition keys

## Setting AWS Budgets

To prevent runaway costs:

1. AWS Console → Billing → Budgets → Create budget
2. Set monthly budget (e.g., $10)
3. Filter to service: "Amazon Bedrock"
4. Set alerts at 50%, 80%, 100%
5. Add email/SNS notifications
