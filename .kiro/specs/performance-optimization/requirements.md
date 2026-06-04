# Requirements Document

## Introduction

This document defines the requirements for performance optimization of the existing ontology-based NLP query system. The system currently suffers from significant latency: spoke agent data retrieval (~17s), visualization rendering (~15s), and guardrail checks (~1-2s). The optimization focuses on reducing LLM call latency through prompt compression, parallel execution of independent pipeline stages, intelligent caching, progressive response delivery, and streamlining guardrails.

All optimizations must preserve functional correctness. The spoke agent and visualization agent retain their LLM reasoning capabilities (required for complex data source queries and dynamic chart generation). Only Claude 3.5 Haiku is used as the LLM model.

---

## Glossary

- **System**: The complete ontology-based NLP query system being optimized.
- **Pipeline**: The processing flow: NLP_Translator → Orchestrator_Hub → Spoke_Agent → Guardrail_Layer → Visualization_Agent.
- **NLP_Translator**: Classifies natural language queries into structured intents using Bedrock Claude.
- **Orchestrator_Hub**: Dispatches structured intents to spoke agents based on ontology entity resolution.
- **Spoke_Agent**: A Strands Agent (LLM-powered) that reasons about how to query data sources. Needed because complex/vague queries against large data stores require LLM interpretation.
- **Visualization_Agent**: A Strands Agent (LLM-powered) that receives structured data from the spoke agent and generates dynamic, interactive chart specifications with statistical insights.
- **Guardrail_Layer**: Validates responses against safety and policy rules. Uses either Bedrock Guardrails API OR local regex rules (not both).
- **Bedrock_Guardrails_API**: Amazon Bedrock's managed content filtering service (`apply_guardrail`).
- **Local_Rules_Engine**: Regex/keyword-based rule evaluation (can be dropped in favor of Bedrock Guardrails).
- **Classification_Cache**: Cache storing query type classifications keyed by normalized query + entity_refs.
- **Result_Cache**: Existing in-memory cache for orchestrator responses.
- **Guardrail_Cache**: Cache storing validation results keyed by content hash.
- **Progressive_Response**: Pattern where statistics are returned immediately while chart generation continues.
- **Haiku_Model**: Claude 3.5 Haiku (`us.anthropic.claude-3-5-haiku-20241022-v1:0`).

---

## Requirements

---

### Requirement 1: Optimize Spoke Agent LLM Call Latency

**User Story:** As a User, I want data retrieval completed in single-digit seconds, so that I can interact with the system without long waits.

#### Acceptance Criteria

1. THE Spoke_Agent SHALL retain LLM reasoning via Strands Agent for data source tool selection and query interpretation, as complex or vague queries against large data stores require LLM understanding.
2. WHEN the Spoke_Agent receives a Structured_Intent, THE Spoke_Agent's system prompt SHALL be concise (under 200 tokens) and contain only the minimum instructions needed for tool selection and data retrieval.
3. THE Spoke_Agent's prompt to the LLM SHALL include only the query_type, entity_refs, and a brief one-line description of each available tool — not full schema dumps or verbose instructions.
4. THE Spoke_Agent SHALL instruct the LLM to respond only with the tool call (no explanation, no markdown, no commentary) to minimize output tokens.
5. THE Spoke_Agent SHALL return a structured AgentResult within 8 seconds of receiving a dispatch request for a single-source query.
6. THE Spoke_Agent SHALL set max_tokens to 500 for the LLM response (sufficient for tool call JSON, not wasteful for text generation).

---

### Requirement 2: Visualization Agent with Dynamic Interactive Chart Generation

**User Story:** As a User, I want query results displayed as dynamic, interactive visualizations with statistical insights, so that I can explore and understand my data visually.

#### Acceptance Criteria

1. THE Visualization_Agent SHALL be a separate Strands Agent (LLM-powered) that receives structured data from the Spoke_Agent and generates dynamic, interactive chart specifications.
2. WHEN the Visualization_Agent receives structured data, THE Agent SHALL analyze the data shape, query context, and statistical properties to select the optimal chart type.
3. THE Visualization_Agent SHALL generate Chart.js-compatible specifications that include interactive features: tooltips, hover effects, click handlers, zoom capabilities, and responsive sizing.
4. THE Visualization_Agent SHALL include statistical annotations in the chart specification: trend lines, averages, min/max markers, and confidence intervals where applicable.
5. THE Visualization_Agent SHALL produce a human-readable description explaining what the visualization shows, key insights from the data, and notable statistical patterns.
6. THE Visualization_Agent's system prompt SHALL be concise (under 250 tokens) with clear directives on output format.
7. THE Visualization_Agent SHALL instruct the LLM to return a single JSON object containing chart_type, chart_data (Chart.js spec), and description — no surrounding text.
8. THE Visualization_Agent SHALL complete chart generation within 10 seconds of receiving the validated response.
9. IF the Visualization_Agent LLM call fails or times out, THEN THE System SHALL fall back to the deterministic rule-based chart selector.

---

### Requirement 3: Streamline Guardrail Checks

**User Story:** As a system operator, I want guardrail validation to be fast and non-redundant, so that content safety checks do not significantly contribute to end-to-end latency.

#### Acceptance Criteria

1. THE System SHALL use Bedrock Guardrails API as the sole content filtering mechanism, dropping the local regex/keyword rules engine to avoid redundant checking.
2. WHEN the System performs input guardrail validation, THE System SHALL call the Bedrock Guardrails API with source="INPUT" and process the result.
3. WHEN the Guardrail_Layer performs output validation, THE Guardrail_Layer SHALL call the Bedrock Guardrails API with source="OUTPUT" and process the result.
4. THE System SHALL NOT run both Bedrock Guardrails AND local regex rules on the same content (eliminates redundancy).
5. IF the Bedrock Guardrails API is unavailable, THEN THE System SHALL fail open (allow the content through with a structured warning log).

---

### Requirement 4: Parallel Execution of Independent Pipeline Stages

**User Story:** As a User, I want independent processing steps to run concurrently, so that end-to-end query time is reduced by overlapping non-dependent operations.

#### Acceptance Criteria

1. WHEN the NLP_Translator begins processing a query, THE NLP_Translator SHALL execute entity resolution (Ontology_Store lookup) and query history bias lookup (Query_History_Store search) concurrently.
2. WHEN the Orchestrator_Hub dispatches to multiple Spoke_Agents, THE Orchestrator_Hub SHALL dispatch to all resolved agents concurrently.
3. WHEN the NLP_API receives a query, THE System SHALL run input guardrail checking and NLP entity resolution in parallel (both are independent of each other).
4. THE System SHALL not introduce parallel execution between pipeline stages that have data dependencies (NLP must complete before Orchestrator dispatch; Spoke must complete before Guardrail validation; Guardrail must complete before Visualization).

---

### Requirement 5: Intelligent Caching

**User Story:** As a system operator, I want repeated computations cached, so that identical queries are served faster without redundant LLM calls.

#### Acceptance Criteria

1. THE System SHALL maintain a Classification_Cache that stores query type classification results keyed by the combination of normalized query text and sorted entity_refs.
2. WHEN the Classification_Cache contains a result for the current query, THE NLP_Translator SHALL return the cached classification without invoking Bedrock Claude.
3. THE Classification_Cache SHALL store at most 1000 entries with LRU eviction.
4. THE Result_Cache (existing) SHALL continue caching orchestrator responses keyed by the deterministic intent hash.
5. THE System SHALL maintain a Guardrail_Cache that stores validation pass/fail results keyed by SHA-256 hash of the response content.
6. WHEN the Guardrail_Cache contains a "passed" result for the current content hash, THE Guardrail_Layer SHALL skip validation and return the cached result.
7. THE Guardrail_Cache SHALL store at most 500 entries with LRU eviction.

---

### Requirement 6: Progressive Response Delivery

**User Story:** As a User, I want to see data statistics immediately while the visualization chart is being generated, so that I have useful information without waiting for the full rendered output.

#### Acceptance Criteria

1. WHEN the Spoke_Agent returns structured data, THE System SHALL compute a statistical summary (totals, averages, counts, ranges) immediately from the raw data.
2. THE statistical summary SHALL be included in the final response alongside the chart specification so the UI can render statistics first.
3. THE response structure SHALL include both a `text_content` field (statistics, populated immediately) and a `chart_data` field (visualization spec, populated after LLM reasoning).
4. THE progressive delivery SHALL use the existing single HTTP JSON response (no WebSockets) to avoid connection upgrade latency overhead.
5. THE statistical summary SHALL be generated within 50 milliseconds of data availability (pure computation, no LLM).

---

### Requirement 7: Model Usage Verification

**User Story:** As a system operator, I want to verify each service is using the correct model, so that costs are predictable and no component inadvertently uses a more expensive model.

#### Acceptance Criteria

1. EACH service that invokes a Bedrock model SHALL reference the DEFAULT_MODEL_ID constant from src/config.py.
2. THE DEFAULT_MODEL_ID SHALL be set to the Haiku_Model (`us.anthropic.claude-3-5-haiku-20241022-v1:0`).
3. IF a future requirement mandates a specific service use a different model, THEN THAT service SHALL define its own model constant with clear documentation of why the override is needed.
4. THE cost tracking system SHALL log the model_id for every invocation, enabling audits of which models are actually being used per component.

---

### Requirement 8: Preserve Functional Correctness

**User Story:** As a User, I want the optimized system to produce the same results as before, so that performance improvements do not come at the cost of accuracy.

#### Acceptance Criteria

1. WHEN the Spoke_Agent processes a Structured_Intent with the optimized prompt, THE Agent SHALL return data results equivalent to the previous implementation for the same input.
2. WHEN the Visualization_Agent generates a chart specification, THE specification SHALL be a valid Chart.js-compatible object with the same structural schema as the existing RenderedOutput model.
3. THE NLP_Translator SHALL produce identical entity_refs and query_type for equivalent input queries after any prompt optimization.
4. IF the optimized pipeline encounters an error, THEN THE System SHALL return the same structured error response format (error_code, error_message, query_id).
5. THE System SHALL pass all existing property tests and unit tests after optimization.
