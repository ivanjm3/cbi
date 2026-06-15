# Design Document: Redshift Data Source Integration

## Overview

This design adds Amazon Redshift as a new data source to the Conversational BI application by creating a dedicated Redshift Spoke Agent that participates in the existing hub-and-spoke architecture. The integration follows established patterns: a new FastAPI service registers with the Orchestrator Hub, receives `StructuredIntent` payloads routed by `entity_ref` overlap, translates them to SQL via a Schema Registry, executes queries through the boto3 Redshift Data API (no persistent connections), and returns `AgentResult` responses compatible with the visualization pipeline.

Key design decisions:
- **Redshift Data API over JDBC**: Uses `boto3 redshift-data` for serverless SQL execution — no connection pools, no driver dependencies, and native AWS IAM integration.
- **Schema Registry for SQL generation**: A static configuration maps ontology concepts to Redshift table/column metadata, enabling deterministic SQL generation without LLM involvement.
- **Deterministic routing**: Like the existing spoke agent, the Redshift spoke agent uses entity_ref matching for fast, predictable query routing without LLM overhead.

## Architecture

```mermaid
graph TB
    subgraph "Orchestrator Hub (port 8002)"
        OH[Orchestrator Hub]
        AR[Agent Registry]
    end

    subgraph "Existing Spoke Agent (port 8010)"
        SA[Spoke Agent]
        S3D[S3 JSON/CSV Sources]
    end

    subgraph "Redshift Spoke Agent (port 8011)"
        RSA[Redshift Spoke Agent<br/>FastAPI]
        SG[SQL Generator]
        SR[Schema Registry]
        RC[Redshift Connector]
    end

    subgraph "AWS"
        RD[Redshift Data API<br/>boto3 redshift-data]
        RS[Redshift Cluster<br/>"talktodata" us-east-1]
    end

    subgraph "Ontology"
        OS[Ontology Store]
        EO[Enterprise Ontology<br/>+ 3 Redshift concepts]
    end

    OH -->|dispatch intent| SA
    OH -->|dispatch intent| RSA
    RSA --> SG
    SG --> SR
    RSA --> RC
    RC --> RD
    RD --> RS
    OH --> AR
    AR -->|entity_ref routing| OS
    OS --> EO
```

### Request Flow

1. User query → NLP Translator → `StructuredIntent` with Redshift entity_refs
2. Orchestrator Hub resolves `redshift-spoke-agent` via entity_ref overlap in Agent Registry
3. Hub dispatches `StructuredIntent` to `POST /agents/redshift-spoke-agent/invoke`
4. Redshift Spoke Agent:
   - Validates intent schema
   - SQL Generator resolves entity_refs via Schema Registry → table/columns
   - SQL Generator produces parameterized SQL based on `query_type`
   - Redshift Connector executes SQL via `redshift-data` API with polling
   - Connector returns column metadata + row data
5. Spoke agent formats response as `AgentResult` with appropriate `data_type`
6. Orchestrator Hub returns `OrchestratorResponse` to visualization pipeline

## Components and Interfaces

### 1. Redshift Connector (`src/services/redshift_connector.py`)

Manages SQL execution against Redshift via the boto3 `redshift-data` client.

```python
class RedshiftConnector:
    """Executes SQL against Redshift via the Data API with polling."""

    def __init__(self, config: RedshiftConfig):
        """Initialize with cluster config from env vars."""

    async def execute_statement(self, sql: str, parameters: list[dict] | None = None) -> RedshiftResult:
        """Submit SQL, poll for completion, return results."""

    async def validate_connectivity(self) -> bool:
        """Test connectivity by executing a simple query."""

    def _poll_statement(self, statement_id: str) -> str:
        """Poll statement status at 500ms-2s intervals, max 30s."""

    def _get_result_set(self, statement_id: str) -> RedshiftResult:
        """Retrieve column metadata and row data for a completed statement."""
```

**Configuration** (`RedshiftConfig`):
| Field | Env Variable | Default |
|-------|-------------|---------|
| cluster_id | REDSHIFT_CLUSTER_ID | "talktodata" |
| database | REDSHIFT_DATABASE | "analytics" |
| db_user | REDSHIFT_DB_USER | "admin" |
| region | REDSHIFT_REGION | "us-east-1" |

### 2. Schema Registry (`src/services/schema_registry.py`)

Static configuration mapping ontology concepts to Redshift table metadata.

```python
class ColumnClassification(str, Enum):
    CATEGORICAL = "categorical"  # GROUP BY, WHERE equality
    NUMERIC = "numeric"          # Aggregate functions (SUM, AVG, etc.)
    IDENTIFIER = "identifier"    # SELECT, WHERE equality only

class ColumnDef(BaseModel):
    name: str
    classification: ColumnClassification
    sql_type: str

class FilterMapping(BaseModel):
    keyword: str
    target_column: str
    operator: Literal["equals", "in", "greater_than", "less_than", "between", "like"]

class TableMapping(BaseModel):
    concept_id: str
    table_name: str
    columns: list[ColumnDef]
    filter_mappings: list[FilterMapping]

class SchemaRegistry:
    """Maps ontology concept_ids to Redshift table metadata."""

    def resolve(self, entity_ref: str) -> TableMapping | None:
        """Resolve entity_ref to table mapping."""

    def get_numeric_columns(self, table_name: str) -> list[ColumnDef]:
        """Get columns classified as numeric for a given table."""

    def get_categorical_columns(self, table_name: str) -> list[ColumnDef]:
        """Get columns classified as categorical for a given table."""

    def validate_against_redshift(self, connector: RedshiftConnector) -> list[str]:
        """Validate all mapped tables exist in Redshift. Returns list of valid concept_ids."""
```

### 3. SQL Generator (`src/services/sql_generator.py`)

Translates `StructuredIntent` into parameterized SQL using the Schema Registry.

```python
class GeneratedQuery(BaseModel):
    sql: str
    parameters: list[dict[str, Any]]
    table_name: str
    query_type: str

class SQLGeneratorError(BaseModel):
    error_type: Literal["UNRESOLVED_ENTITY", "INVALID_QUERY_TYPE"]
    description: str

class SQLGenerator:
    """Translates StructuredIntent to parameterized SQL via Schema Registry."""

    def __init__(self, schema_registry: SchemaRegistry):
        """Initialize with schema registry."""

    def generate(self, intent: StructuredIntent) -> GeneratedQuery | SQLGeneratorError:
        """Generate SQL from a structured intent."""

    def _generate_lookup(self, table: TableMapping, intent: StructuredIntent) -> GeneratedQuery:
        """SELECT ... WHERE ... LIMIT 1000"""

    def _generate_aggregation(self, table: TableMapping, intent: StructuredIntent) -> GeneratedQuery:
        """SELECT aggregate(numeric_cols) ... GROUP BY categorical_cols"""

    def _generate_comparison(self, table: TableMapping, intent: StructuredIntent) -> GeneratedQuery:
        """SELECT first_categorical, SUM(numeric_cols) ... GROUP BY first_categorical"""
```

### 4. Redshift Spoke Agent (`src/agents/redshift_spoke_agent.py`)

FastAPI application exposing the invoke endpoint for Redshift queries.

```python
app = FastAPI(title="Redshift Spoke Agent", version="1.0.0")

AGENT_ID = "redshift-spoke-agent"

@app.post("/agents/redshift-spoke-agent/invoke")
async def invoke_agent(body: InvokeRequest) -> JSONResponse:
    """Process structured intent: generate SQL → execute → format AgentResult."""

@app.get("/health")
async def health_check() -> dict:
    """Return service health including Redshift connectivity status."""
```

**Data type mapping:**
| query_type | data_type | Payload structure |
|-----------|-----------|-------------------|
| lookup | tabular | `{columns: [...], rows: [[...]], row_count: N}` |
| aggregation | aggregation | `{aggregations: {col: {sum, avg, ...}}, row_count: N}` |
| comparison | comparison | `{group_by: "col", groups: {key: {col: {sum, avg}}}, row_count: N}` |

### 5. Ontology Extension

Three new concepts added to `data/ontology/enterprise_ontology.json`:

| concept_id | domain | data_source | agent_id | numeric properties |
|-----------|--------|-------------|----------|-------------------|
| ontology:sales_transactions | finance | redshift | redshift-spoke-agent | quantity, total_amount |
| ontology:customer_segments | customers | redshift | redshift-spoke-agent | lifetime_value, total_orders |
| ontology:employee_performance | hr | redshift | redshift-spoke-agent | quarterly_target, quarterly_actual, deals_closed, customer_satisfaction_score |

Relationships use `relation_type: "grouped_by"` with `join_key` property linking to shared dimension concepts (`ontology:region`, `ontology:product_category`).

### 6. Agent Registration

Added to `src/services/register_agents.py`:

```python
{
    "agent_id": "redshift-spoke-agent",
    "agent_name": "Redshift Spoke Agent",
    "data_source": "redshift",
    "endpoint_url": "http://localhost:8011",
    "entity_refs": [
        "ontology:sales_transactions",
        "ontology:customer_segments",
        "ontology:employee_performance",
    ],
}
```

## Data Models

### RedshiftConfig

```python
class RedshiftConfig(BaseModel):
    cluster_id: str = Field(default="talktodata")
    database: str = Field(default="analytics")
    db_user: str = Field(default="admin")
    region: str = Field(default="us-east-1")

    @classmethod
    def from_env(cls) -> "RedshiftConfig":
        return cls(
            cluster_id=os.environ.get("REDSHIFT_CLUSTER_ID", "talktodata"),
            database=os.environ.get("REDSHIFT_DATABASE", "analytics"),
            db_user=os.environ.get("REDSHIFT_DB_USER", "admin"),
            region=os.environ.get("REDSHIFT_REGION", "us-east-1"),
        )
```

### RedshiftResult

```python
class RedshiftResult(BaseModel):
    columns: list[dict[str, str]]  # [{"name": "col", "type": "VARCHAR"}, ...]
    rows: list[list[Any]]
    row_count: int
    statement_id: str
```

### RedshiftError

```python
class RedshiftError(BaseModel):
    error_type: Literal["TIMEOUT", "AUTH_FAILURE", "QUERY_FAILURE", "CONNECTION_ERROR"]
    description: str
    elapsed_seconds: float | None = None
```

### Schema Registry Table Definitions

```python
SCHEMA_MAPPINGS: list[TableMapping] = [
    TableMapping(
        concept_id="ontology:sales_transactions",
        table_name="sales_transactions",
        columns=[
            ColumnDef(name="transaction_id", classification="identifier", sql_type="VARCHAR"),
            ColumnDef(name="transaction_date", classification="categorical", sql_type="DATE"),
            ColumnDef(name="customer_id", classification="identifier", sql_type="VARCHAR"),
            ColumnDef(name="product_name", classification="categorical", sql_type="VARCHAR"),
            ColumnDef(name="category", classification="categorical", sql_type="VARCHAR"),
            ColumnDef(name="region", classification="categorical", sql_type="VARCHAR"),
            ColumnDef(name="quantity", classification="numeric", sql_type="INTEGER"),
            ColumnDef(name="unit_price", classification="numeric", sql_type="DECIMAL"),
            ColumnDef(name="total_amount", classification="numeric", sql_type="DECIMAL"),
            ColumnDef(name="payment_method", classification="categorical", sql_type="VARCHAR"),
        ],
        filter_mappings=[
            FilterMapping(keyword="category", target_column="category", operator="equals"),
            FilterMapping(keyword="region", target_column="region", operator="equals"),
            FilterMapping(keyword="payment_method", target_column="payment_method", operator="equals"),
            FilterMapping(keyword="product_name", target_column="product_name", operator="like"),
        ],
    ),
    TableMapping(
        concept_id="ontology:customer_segments",
        table_name="customer_segments",
        columns=[
            ColumnDef(name="customer_id", classification="identifier", sql_type="VARCHAR"),
            ColumnDef(name="customer_name", classification="categorical", sql_type="VARCHAR"),
            ColumnDef(name="segment", classification="categorical", sql_type="VARCHAR"),
            ColumnDef(name="lifetime_value", classification="numeric", sql_type="DECIMAL"),
            ColumnDef(name="signup_date", classification="categorical", sql_type="DATE"),
            ColumnDef(name="region", classification="categorical", sql_type="VARCHAR"),
            ColumnDef(name="total_orders", classification="numeric", sql_type="INTEGER"),
            ColumnDef(name="last_order_date", classification="categorical", sql_type="DATE"),
        ],
        filter_mappings=[
            FilterMapping(keyword="segment", target_column="segment", operator="equals"),
            FilterMapping(keyword="region", target_column="region", operator="equals"),
        ],
    ),
    TableMapping(
        concept_id="ontology:employee_performance",
        table_name="employee_performance",
        columns=[
            ColumnDef(name="employee_id", classification="identifier", sql_type="VARCHAR"),
            ColumnDef(name="employee_name", classification="categorical", sql_type="VARCHAR"),
            ColumnDef(name="department", classification="categorical", sql_type="VARCHAR"),
            ColumnDef(name="role", classification="categorical", sql_type="VARCHAR"),
            ColumnDef(name="hire_date", classification="categorical", sql_type="DATE"),
            ColumnDef(name="region", classification="categorical", sql_type="VARCHAR"),
            ColumnDef(name="quarterly_target", classification="numeric", sql_type="DECIMAL"),
            ColumnDef(name="quarterly_actual", classification="numeric", sql_type="DECIMAL"),
            ColumnDef(name="deals_closed", classification="numeric", sql_type="INTEGER"),
            ColumnDef(name="customer_satisfaction_score", classification="numeric", sql_type="DECIMAL"),
        ],
        filter_mappings=[
            FilterMapping(keyword="department", target_column="department", operator="equals"),
            FilterMapping(keyword="region", target_column="region", operator="equals"),
            FilterMapping(keyword="role", target_column="role", operator="equals"),
        ],
    ),
]
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Generated SQL is syntactically valid

*For any* valid `StructuredIntent` whose entity_refs resolve in the Schema Registry, the SQL Generator SHALL produce a SQL string that can be parsed without error by a standard SQL parser.

**Validates: Requirements 3.9**

### Property 2: SQL structure matches query type

*For any* valid `StructuredIntent` with resolvable entity_refs:
- If `query_type` is "lookup", the generated SQL SHALL be a SELECT with a WHERE clause and `LIMIT 1000`
- If `query_type` is "aggregation", the generated SQL SHALL contain at least one aggregate function (SUM, AVG, COUNT, MIN, or MAX) and a GROUP BY clause on all categorical columns
- If `query_type` is "comparison", the generated SQL SHALL contain a GROUP BY on the first categorical column from entity_refs and SUM applied to numeric columns

**Validates: Requirements 3.1, 3.2, 3.3**

### Property 3: Parameterized queries prevent SQL injection

*For any* string value used as a filter (including strings containing SQL keywords, quotes, semicolons, or comment sequences), the SQL Generator SHALL never interpolate the value directly into the SQL string — all filter values SHALL appear only in the parameters list, with the SQL using placeholder syntax.

**Validates: Requirements 3.4**

### Property 4: Unresolved entity_refs produce errors

*For any* entity_ref string that is not present in the Schema Registry's concept mappings, the SQL Generator SHALL return an error with `error_type` "UNRESOLVED_ENTITY" containing the unresolved entity_ref identifier.

**Validates: Requirements 3.6**

### Property 5: Multi-table entity_refs resolve to first table only

*For any* `StructuredIntent` whose entity_refs resolve to more than one distinct table in the Schema Registry, the generated SQL SHALL reference only the first resolved table and include only entity_refs belonging to that table.

**Validates: Requirements 3.7**

### Property 6: Result parsing preserves column metadata and rows

*For any* valid Redshift Data API response containing column metadata and row data, the Redshift Connector's result parser SHALL produce a `RedshiftResult` where the number of columns matches the metadata count and each row has exactly as many values as there are columns.

**Validates: Requirements 2.7**

### Property 7: Polling respects interval and timeout constraints

*For any* SQL statement execution, the Redshift Connector's polling loop SHALL:
- Wait between 500ms and 2000ms between consecutive polls
- Not exceed 30 seconds of total elapsed time before cancelling
- Return a TIMEOUT error if the statement has not completed within 30 seconds

**Validates: Requirements 2.3, 2.4**

### Property 8: Query type maps to correct data_type in response

*For any* valid `StructuredIntent` that executes successfully, the Redshift Spoke Agent SHALL return an `AgentResult` where `payload.data_type` equals "tabular" for lookup queries, "aggregation" for aggregation queries, and "comparison" for comparison queries.

**Validates: Requirements 4.4**

### Property 9: Invalid request bodies produce INVALID_INTENT errors

*For any* request body that does not conform to the `StructuredIntent` schema (missing required fields, wrong types, empty entity_refs), the Redshift Spoke Agent SHALL return an `AgentResult` with `status` "error" and `error_type` "INVALID_INTENT".

**Validates: Requirements 4.8**

### Property 10: Orchestrator resolves Redshift agent for Redshift entity_refs

*For any* `StructuredIntent` containing at least one entity_ref from the set `{ontology:sales_transactions, ontology:customer_segments, ontology:employee_performance}`, the Orchestrator Hub's agent resolution SHALL include "redshift-spoke-agent" in the resolved candidates.

**Validates: Requirements 6.2**

### Property 11: Schema Registry structural completeness

*For any* table mapping in the Schema Registry:
- Every column SHALL have exactly one classification (categorical, numeric, or identifier)
- Every filter mapping SHALL reference a target_column that exists in the table's column list
- Every filter mapping SHALL specify a valid comparison operator (one of: equals, in, greater_than, less_than, between, like)

**Validates: Requirements 8.1, 8.2, 8.3**

## Error Handling

### Error Classification

| Component | Error Type | Trigger | Recovery |
|-----------|-----------|---------|----------|
| RedshiftConnector | TIMEOUT | Statement exceeds 30s | Cancel statement, return error |
| RedshiftConnector | AUTH_FAILURE | Invalid credentials | Return error, agent reports unhealthy |
| RedshiftConnector | QUERY_FAILURE | SQL execution error | Return error with API description |
| RedshiftConnector | CONNECTION_ERROR | Network/endpoint failure | Return error, agent reports unhealthy |
| SQLGenerator | UNRESOLVED_ENTITY | entity_ref not in Schema Registry | Return error listing unresolved ref |
| SQLGenerator | INVALID_QUERY_TYPE | Unsupported query_type | Return error (defensive) |
| RedshiftSpokeAgent | INVALID_INTENT | Malformed request body | Return AgentResult with error |
| RedshiftSpokeAgent | QUERY_EXECUTION_ERROR | Connector returns error | Propagate as AgentResult error |
| OrchestratorHub | unavailable_agents | Agent HTTP failure/timeout | Add to unavailable list in response |
| SchemaRegistry | Missing table at startup | Table not in Redshift | Log warning, exclude concept |

### Degraded State Behavior

The Redshift Spoke Agent supports a degraded state where:
1. At startup, if Redshift connectivity fails, the agent starts but `/health` returns `{"status": "unhealthy"}`
2. If Schema Registry validation finds missing tables, those concepts are excluded from available entity_refs
3. If ALL tables are missing, the agent refuses to start (hard failure)

### Error Propagation

All errors from the Redshift Connector are wrapped into `AgentResult` with `status: "error"` and propagated to the Orchestrator Hub. The Hub handles agent errors via its standard `unavailable_agents` mechanism.

## Testing Strategy

### Property-Based Tests (Hypothesis)

Property-based tests are the primary validation method for the SQL Generator, Schema Registry, and result parsing logic. These components have pure-function characteristics with large input spaces.

**Library**: Hypothesis (already in dev dependencies)
**Minimum iterations**: 100 per property
**Tag format**: `Feature: redshift-data-source-integration, Property {N}: {description}`

Key property test targets:
- SQL Generator: Properties 1-5 (syntax validity, structural correctness, injection prevention, error handling, multi-table resolution)
- Redshift Connector result parser: Property 6
- Redshift Connector polling logic: Property 7 (with mocked time)
- Spoke Agent response formatting: Properties 8-9
- Orchestrator routing: Property 10
- Schema Registry validation: Property 11

### Unit Tests (pytest)

Example-based tests for specific scenarios:
- Provisioning script error handling (connection failure, table exists)
- Auth failure and query failure error classification
- Health endpoint response structure
- Startup connectivity validation (success/failure paths)
- Ontology concept structure verification
- Agent registration request format

### Integration Tests

End-to-end tests requiring a Redshift cluster (or LocalStack mock):
- Provisioning script creates tables and seeds data
- Full flow: StructuredIntent → SQL → Redshift → AgentResult
- Orchestrator dispatches to Redshift spoke agent and receives response
- Schema Registry validation against real Redshift tables

### Test Organization

```
tests/
├── properties/
│   ├── test_sql_generator.py          # Properties 1-5
│   ├── test_redshift_result_parsing.py # Property 6
│   ├── test_redshift_polling.py        # Property 7
│   ├── test_redshift_spoke_response.py # Properties 8-9
│   ├── test_redshift_routing.py        # Property 10
│   └── test_schema_registry.py         # Property 11
├── unit/
│   ├── test_redshift_connector.py
│   ├── test_redshift_spoke_agent.py
│   ├── test_redshift_ontology.py
│   └── test_redshift_registration.py
└── integration/
    ├── test_redshift_provisioning.py
    └── test_redshift_end_to_end.py
```
