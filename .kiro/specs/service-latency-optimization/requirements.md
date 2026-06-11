# Requirements Document

## Introduction

This feature addresses critical latency bottlenecks in the multi-service query pipeline (NLP → Orchestrator → Guardrail → Visualization). The current architecture suffers from excessive HTTP overhead (4 sequential hops totaling 270s in timeouts), lack of connection pooling, no S3 caching, and inefficient LLM usage patterns. The goal is to reduce end-to-end latency by 40–70% through HTTP chain optimization, connection pooling, caching, smarter orchestrator routing, and LLM prompt reduction.

## Glossary

- **Query_Pipeline**: The end-to-end service chain that processes a user query: NLP Translator → Orchestrator Hub → Guardrail Layer → Visualization Renderer
- **NLP_API**: The FastAPI gateway service (`nlp_api.py`) that accepts user queries and orchestrates calls to downstream services
- **Orchestrator_Hub**: The service responsible for routing structured intents to the appropriate spoke agent for data retrieval
- **Guardrail_Layer**: The service that validates orchestrator responses against content policies before rendering
- **Visualization_Renderer**: The service that generates chart configurations from validated data using an LLM agent
- **Connection_Pool**: A managed set of reusable HTTP connections configured via `httpx.Limits` to avoid per-request connection establishment overhead
- **S3_Cache**: An in-memory LRU cache with TTL for S3 file contents to avoid repeated fetches of unchanged data
- **Direct_Dispatch**: A routing path in the Orchestrator Hub that bypasses LLM classification for simple query types (lookup, aggregation)
- **Semantic_Cache**: A cache that matches queries by semantic similarity rather than exact string match, using a cosine similarity threshold
- **Cold_Start**: The initial latency incurred when a service instance or LLM model is loaded for the first time

## Requirements

### Requirement 1: Reduce HTTP Timeout Configuration

**User Story:** As a system operator, I want reduced HTTP timeouts across the query pipeline, so that cascading failures resolve faster and users receive timely error responses instead of waiting minutes.

#### Acceptance Criteria

1. WHEN the NLP_API calls the Orchestrator_Hub, THE NLP_API SHALL use a timeout of 45 seconds
2. WHEN the NLP_API calls the Guardrail_Layer, THE NLP_API SHALL use a timeout of 15 seconds
3. WHEN the NLP_API calls the Visualization_Renderer, THE NLP_API SHALL use a timeout of 60 seconds
4. THE NLP_API SHALL have a maximum total pipeline timeout of 135 seconds across all downstream calls

### Requirement 2: Implement Connection Pooling

**User Story:** As a system operator, I want persistent HTTP connection pooling between services, so that repeated requests reuse established connections and avoid TCP/TLS handshake overhead.

#### Acceptance Criteria

1. THE NLP_API SHALL maintain a shared connection pool with a maximum of 10 keep-alive connections and 20 total connections for downstream service calls
2. THE NLP_API SHALL reuse the shared connection pool across all requests within the same process lifecycle
3. WHEN the NLP_API starts up, THE NLP_API SHALL initialize the connection pool eagerly rather than on first request
4. IF a pooled connection becomes stale, THEN THE NLP_API SHALL discard the connection and establish a new one transparently

### Requirement 3: Merge Guardrail and Visualization Services

**User Story:** As a platform engineer, I want to combine the Guardrail Layer and Visualization Renderer into a single service, so that the pipeline reduces from 4 HTTP hops to 3 and eliminates one network round-trip.

#### Acceptance Criteria

1. THE merged Guardrail_Visualization_Service SHALL accept validated orchestrator responses and perform both content validation and rendering in a single call
2. WHEN the NLP_API calls the merged service, THE NLP_API SHALL make one HTTP request instead of two sequential requests to separate Guardrail and Visualization services
3. THE merged Guardrail_Visualization_Service SHALL preserve all existing guardrail validation logic without modification to policy rules
4. THE merged Guardrail_Visualization_Service SHALL preserve all existing visualization rendering logic without modification to chart generation behavior
5. IF guardrail validation rejects a response, THEN THE merged Guardrail_Visualization_Service SHALL return the rejection immediately without invoking the renderer

### Requirement 4: Reduce LLM Prompt Sizes

**User Story:** As a developer, I want to limit ontology context passed to LLM prompts, so that classification and rendering calls process faster and cost less.

#### Acceptance Criteria

1. WHEN building ontology context for query classification, THE NLP_Translator SHALL include a maximum of 5 ontology concepts in the prompt
2. WHEN multiple ontology concepts are resolved, THE NLP_Translator SHALL select the 5 most relevant concepts based on keyword match score
3. WHEN building prompts for the Visualization_Renderer agent, THE Orchestrator_Hub SHALL limit context payload to the essential data fields required for chart generation

### Requirement 5: Implement S3 File-Level Caching

**User Story:** As a developer, I want in-memory caching of S3 file contents with a TTL, so that repeated data retrievals within a short window avoid redundant S3 reads.

#### Acceptance Criteria

1. THE S3_Cache SHALL cache file contents in memory with a time-to-live of 5 minutes
2. WHEN a cached file is requested within the TTL window, THE S3_Cache SHALL return the cached content without making an S3 API call
3. WHEN the TTL expires for a cached entry, THE S3_Cache SHALL evict the entry and fetch fresh content on the next request
4. THE S3_Cache SHALL use an LRU eviction policy when the cache reaches its maximum capacity
5. IF an S3 fetch fails, THEN THE S3_Cache SHALL return the stale cached content if available and log a warning

### Requirement 6: Pre-warm Frequently Accessed Data

**User Story:** As a system operator, I want frequently accessed S3 files preloaded into cache on service startup, so that the first user requests after deployment avoid cold-start S3 latency.

#### Acceptance Criteria

1. WHEN the Orchestrator_Hub starts up, THE Orchestrator_Hub SHALL preload a configured list of frequently accessed S3 files into the S3_Cache
2. THE Orchestrator_Hub SHALL complete pre-warming within 10 seconds of startup to avoid delaying service readiness
3. IF pre-warming fails for a specific file, THEN THE Orchestrator_Hub SHALL log a warning and continue warming remaining files without blocking startup

### Requirement 7: Expand Direct Dispatch Routing

**User Story:** As a developer, I want the Orchestrator Hub to route "lookup" and "aggregation" query types directly to spoke agents without LLM classification, so that simple queries avoid the 1–3 second LLM routing overhead.

#### Acceptance Criteria

1. WHEN the Orchestrator_Hub receives a structured intent with query_type "lookup", THE Orchestrator_Hub SHALL route directly to the appropriate spoke agent without invoking the LLM routing agent
2. WHEN the Orchestrator_Hub receives a structured intent with query_type "aggregation", THE Orchestrator_Hub SHALL route directly to the appropriate spoke agent without invoking the LLM routing agent
3. WHEN the Orchestrator_Hub receives a structured intent with query_type "comparison", THE Orchestrator_Hub SHALL invoke the LLM routing agent for multi-agent coordination
4. THE Orchestrator_Hub SHALL select the target spoke agent for direct dispatch based on the primary entity reference in the structured intent

### Requirement 8: Implement Streaming Responses for Visualization

**User Story:** As a user, I want visualization results streamed progressively, so that I see partial output faster instead of waiting for the entire chart to generate.

#### Acceptance Criteria

1. WHEN the Visualization_Renderer generates a chart configuration, THE Visualization_Renderer SHALL stream response chunks as they become available from the LLM agent
2. THE NLP_API SHALL forward streamed chunks to the client using Server-Sent Events (SSE)
3. WHEN streaming is active, THE NLP_API SHALL send a latency metadata event after all chunks are delivered
4. IF the streaming connection is interrupted, THEN THE NLP_API SHALL return a partial response with an indication that output is incomplete

### Requirement 9: Normalize Cache Parameters

**User Story:** As a developer, I want cache keys normalized to exclude volatile metadata (timestamps, request IDs), so that semantically identical queries produce cache hits.

#### Acceptance Criteria

1. WHEN computing a cache key for query results, THE Result_Cache SHALL exclude volatile fields including timestamps, query IDs, and correlation IDs from the key computation
2. WHEN computing a cache key, THE Result_Cache SHALL normalize query text by trimming whitespace, converting to lowercase, and sorting entity references
3. THE Result_Cache SHALL produce identical cache keys for queries that differ only in volatile metadata

### Requirement 10: Implement Semantic Similarity Caching

**User Story:** As a developer, I want query results cached with semantic similarity matching, so that paraphrased queries that mean the same thing return cached results instead of reprocessing.

#### Acceptance Criteria

1. WHEN a new query is received, THE Semantic_Cache SHALL compare the query embedding against cached query embeddings using cosine similarity
2. WHEN cosine similarity exceeds 0.85, THE Semantic_Cache SHALL return the cached result without re-executing the query pipeline
3. THE Semantic_Cache SHALL store query embeddings alongside cached results for future similarity comparisons
4. WHEN a cache hit occurs via semantic matching, THE Semantic_Cache SHALL log the match score and original cached query for observability
