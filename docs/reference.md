a) Resume Bullet Points
Here's how I'd present this project on a resume:

Conversational BI Platform | Python, React, AWS Bedrock, FastAPI

Designed and built a full-stack conversational BI system that transforms natural language questions into interactive Chart.js visualizations using a hub-and-spoke microservices architecture (5 FastAPI services)
Integrated Amazon Bedrock (Claude 3.5 Haiku) for NLP intent classification, intelligent chart type selection, and analytical insight generation using the Strands SDK agent framework
Implemented multi-layer caching (LRU at NLP, orchestrator, guardrail, and renderer layers) to minimize LLM costs ($0.002–$0.005 per novel query, $0 for cached queries)
Built content safety pipeline using Amazon Bedrock Guardrails for input/output filtering with fail-open resilience and schema validation via Pydantic
Engineered deterministic fallback paths at every LLM-dependent stage ensuring 100% query resolution rate regardless of Bedrock availability
Developed React/TypeScript frontend with zustand state management, drag-and-drop visualization grid (react-dnd), and responsive Chart.js rendering
Applied property-based testing (Hypothesis) to validate correctness properties across ontology resolution, intent classification, and visualization rendering
b) Interview Explanation
Here's how I'd explain it conversationally in an interview:

"I built a conversational BI system — think of it as a ChatGPT-style interface where business users type natural language questions like 'show me Q4 revenue by region' and get back interactive charts with analytical insights.

Architecture: It's a hub-and-spoke microservices system — five independent Python/FastAPI services, each with a single responsibility. The NLP Translator acts as the gateway, parsing the query and resolving it against a domain ontology stored in S3. The Orchestrator Hub routes to the right data agent based on entity matching. The Spoke Agent retrieves and aggregates data from S3 (JSON/CSV sources). Then the Visualization Renderer — which is the most interesting piece — uses an LLM agent (Claude on Amazon Bedrock) with forced tool-calling to generate production-quality Chart.js configs. There's also a Guardrail Layer for content safety on both input and output.

Key technical decisions: I used Amazon Bedrock's Strands SDK for the agentic components — the orchestrator uses it for complex multi-domain routing, and the renderer uses it with a forced emit_chart tool to guarantee structured output. Every LLM-dependent stage has a deterministic fallback, so the system never fails to produce a result. The caching strategy is layered across all services to minimize Bedrock invocation costs.

Frontend: React with TypeScript, zustand for state, and Chart.js for rendering. The grid layout adapts based on how many visualizations you've generated in a session. It also supports drag-to-reorder, voice input, and session persistence.

Quality: I used property-based testing with Hypothesis to validate correctness properties — things like 'any valid ontology entity must serialize and deserialize consistently' or 'chart type selection always produces a valid Chart.js config type.' This gave me much higher confidence than example-based tests alone.

Deployment: I also designed an alternative deployment path using Bedrock's Return Control pattern, which eliminates Lambda functions entirely — the agent returns tool call parameters directly to the application for local validation. This simplified the IAM requirements significantly."






a) does the system implement (past and future) just an ontology store or does it also utilize a knowledge graph

b) if it doesnt , how useful is a knowledge graph in production scenarios and systems like this

c) is it isnt implemented and does have a significant deliverable without increasing (rather better if it decreases) latency then add / updates tasks.md with this

Kiro
Read file(s)

ontology_store.py

ontology.py
Searched workspace
Check the ontology data files to understand the current graph structure.
Read file(s)

enterprise_ontology.json
Now I have a complete picture. Let me answer your questions:

a) Ontology Store vs. Knowledge Graph
The system currently implements an ontology store — not a knowledge graph. Specifically:

It stores concepts (nodes) and typed relationships (edges) in JSON files on S3, loaded into memory as flat Python dicts.
Traversal is done via linear scans: lookup_concept iterates all definitions, traverse_hierarchy does single-hop neighbor lookups, search_concepts does substring matching on labels.
There's no graph index, no multi-hop pathfinding, no inference engine, no weighted shortest-path computation.
The planned extensions (Phase 3: source_mapping, rank_sources_by_proximity with hop counting) add rudimentary graph traversal but still implement it as BFS/DFS over in-memory lists — no dedicated graph data structure or query engine.

b) Would a Knowledge Graph Add Significant Value?
Yes — meaningfully so in a system like this. Here's why:

What you gain with a proper in-memory knowledge graph layer:

Multi-hop reasoning in O(hops) instead of O(concepts × relationships) — The current linear scan approach gets expensive as the ontology grows. A graph with adjacency indexes makes rank_sources_by_proximity and resolve_sources_for_concept constant-per-hop.

Better query decomposition — When the Query Planner needs to figure out which sources can answer "compare Q1 sales with supplier regions," it needs to traverse the shared dimension (ontology:region) connecting sales_revenue → region ← supplier_info. With a proper graph, this is a standard shortest-path query. Without one, you're writing custom BFS loops per use case.

Semantic similarity via graph embeddings — The design doc mentions "semantic similarity against concept labels and synonyms" (Req 4.3). A graph structure lets you compute similarity from structural position (not just string matching), which is more robust for vague queries.

Latency improvement — Counterintuitively, a well-indexed in-memory graph is faster than the current approach (repeated list scans). Libraries like networkx give you O(1) neighbor lookups and built-in BFS/Dijkstra. The ontology is small enough (~10-50 concepts) to fit entirely in memory, so there's no DB round-trip.

Join key discovery — Cross-source queries need to find common dimensions. A graph makes this "find paths between two concept nodes" — directly supported by shortest-path algorithms.

What you DON'T need:

No external graph database (Neo4j, Neptune) — the ontology is small, an in-memory networkx.DiGraph is sufficient.
No extra network hop — the graph lives in-process alongside the Query Planner.
c) Verdict: Yes, it should be added
A lightweight in-memory knowledge graph (via networkx) adds real value without increasing latency (it actually decreases it for multi-hop traversals). The implementation is small: build a DiGraph from existing ontology data on load, expose graph-native query methods, and use it in the Query Planner's source resolution logic.

Let me update tasks.md to add this:

Read file(s)

.kiro/specs/agent-multi-source-retrieval/tasks.md 118 - 181

.kiro/specs/agent-multi-source-retrieval/tasks.md 180 - 246
Now I have full context. The knowledge graph should be inserted into Phase 3 since that's the ontology extension phase, and it directly enhances tasks 3.2 and 3.6 (source-aware traversal and ranking). I'll insert it between 3.1 (which adds source_mapping to the model) and 3.2 (which needs graph traversal). The graph layer becomes the backbone that 3.2's methods operate on.

Error(s) while editing

tasks.md

Operation was aborted by user or system. The agent has seen this error and will try a different approach to write the file if needed.
Est. Credits Used: 0.94(?)
Elapsed time: 1m 34s


Checkpoint
Restore
resume

Kiro
Read file(s)

tasks.md 188 - 231
Now I'll insert the knowledge graph tasks into Phase 3. The logical placement is after task 3.1 (extend ontology model) and before 3.2 (source-aware methods), since the graph index should be built first and then the source-aware methods should use it. I'll add a new task 3.2 for the knowledge graph and renumber subsequent tasks.

Accepted edits to

tasks.md


Now I need to update the remaining Phase 3 tasks that followed (3.7 → 3.9, 3.8 → 3.10):

Read file(s)

tasks.md 238 - 261
I need to fix the stabilization checkpoint numbering — it's still 3.8 but should be 3.10:

Accepted edits to

tasks.md


Now let me also update the notes section to mention the knowledge graph addition and the new property test count:

Read file(s)

tasks.md 290 - 331
Accepted edits to

tasks.md


Done. Here's the summary of what was added to tasks.md:

New tasks in Phase 3:

3.2 — Build in-memory Knowledge Graph index from ontology data — Creates 
knowledge_graph.py
 backed by networkx.DiGraph. Provides O(1) neighbor lookups, shortest-path computation, BFS traversal with optional hop bounds, and crucially find_connecting_dimensions() for automatic join key discovery between sources. Built on load from existing ontology data, zero network latency added.

3.3 — Property tests for Knowledge Graph (optional) — Three new properties:

P14: Graph construction completeness
P15: Shortest path correctness
P16: Join key discovery correctness
Modified tasks:

3.4 (was 3.2): Source-aware methods now explicitly use the KnowledgeGraph internally instead of manual BFS loops
3.8 (was 3.6): Query Planner now also uses find_connecting_dimensions() for cross-source join key inference
3.9/3.10: Renumbered (ontology data update + stabilization checkpoint)
Why this helps, not hurts latency:

The current traverse_hierarchy and search_concepts methods scan all concepts × relationships linearly. A networkx.DiGraph gives adjacency in O(1) and BFS/Dijkstra built-in.
The graph lives in-process (no extra network hop, no external DB).
For the ~10-50 concept ontology, graph build time is negligible (<1ms).
The big win is in multi-source decomposition: finding join keys between two source-mapped concepts becomes a simple "find shared neighbors" call instead of custom traversal code.