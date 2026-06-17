# Architecture Updates for 6-Feature Enhancement

## Current Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Chat Interface                                           │  │
│  │  ├─ ChatThread (messages)                                 │  │
│  │  ├─ Cards (visualizations)                                │  │
│  │  │  ├─ ChartRenderer                                      │  │
│  │  │  └─ CardToolbar (viz type dropdown) ✅                 │  │
│  │  └─ Strands (multi-turn) - exists but messages not       │  │
│  │     rendering dynamically ⚠️                               │  │
│  │                                                            │  │
│  │  Store: useSessionStore (Zustand)                        │  │
│  │  ├─ chatThread                                            │  │
│  │  ├─ cards                                                 │  │
│  │  ├─ strands (sessions only, localStorage)                │  │
│  │  └─ actions (submitQuery, changeCardVisualizationType)   │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↓ queryApi.ts
┌─────────────────────────────────────────────────────────────────┐
│                        BACKEND                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  NLP API (nlp_api.py)                                     │  │
│  │  ├─ Step 0: Meta-query detection ✅                       │  │
│  │  ├─ Step 0.5: ⚠️ NEED: Global cache check                 │  │
│  │  ├─ Step 0.75: ⚠️ NEED: Ontology validation              │  │
│  │  ├─ Step 1: NLP Translation                              │  │
│  │  ├─ Step 2: Orchestrator                                 │  │
│  │  ├─ Step 3: Guardrails                                   │  │
│  │  ├─ Step 3.5: ⚠️ NEED: Text-only detection               │  │
│  │  ├─ Step 4: Visualization Renderer                       │  │
│  │  └─ Step 5: Cache storage (after Step 4)                 │  │
│  │                                                            │  │
│  │  Supporting Services:                                     │  │
│  │  ├─ OntologyStore                                         │  │
│  │  ├─ NLP Translator                                        │  │
│  │  ├─ Orchestrator Hub                                      │  │
│  │  ├─ Visualization Agent                                  │  │
│  │  ├─ ⚠️ NEED: Cache Layer (Redis)                         │  │
│  │  ├─ ⚠️ NEED: Ontology Validator                          │  │
│  │  └─ ⚠️ NEED: Text-Only Detector                          │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Data Layer                                               │  │
│  │  ├─ Redshift (structured data)                            │  │
│  │  ├─ Ontology JSON (enterprise entities)                   │  │
│  │  └─ ⚠️ NEED: Redis (query cache)                          │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## New Components & Modifications

### Frontend Components (NEW)

```
frontend/src/components/
├─ ConversationStrand.tsx ✅ (NEW - Requirement #5)
│  ├─ Displays strand messages
│  ├─ Handles follow-up input
│  └─ ✅ FIXES: Chat visibility issue (proper Zustand selector)
│
└─ CardHistoryDropdown.tsx ✅ (NEW - Requirement #2)
   ├─ Collapsible query history
   ├─ Metadata display
   └─ Column stats
```

### Backend Services (NEW)

```
src/services/
├─ cache_layer.py ✅ (NEW - Requirement #3)
│  ├─ GlobalQueryCache class
│  ├─ Redis backend
│  └─ Hash-based key generation
│
├─ ontology_validator.py ✅ (NEW - Requirement #4)
│  ├─ OntologyValidator class
│  ├─ Entity existence validation
│  └─ Suggestions for typos
│
└─ text_only_detector.py ✅ (NEW - Requirement #6)
   ├─ TextOnlyDetector class
   ├─ Query pattern matching
   └─ TextSummaryGenerator helper
```

---

## Data Flow: Updated Query Pipeline

### Existing Flow
```
User Query
  ↓
queryApi.ts
  ↓
nlp_api.py
  │
  ├─ Step 0: Meta-query check ✅
  ├─ Step 1: NLP Translation
  ├─ Step 2: Orchestrator
  ├─ Step 3: Guardrails
  ├─ Step 4: Visualization
  └─ Return RenderedOutput
```

### Updated Flow (with new steps)

```
User Query
  ↓
queryApi.ts
  ↓
nlp_api.py
  │
  ├─ Step 0: Meta-query check ✅
  │
  ├─ Step 0.5: ⭐ CACHE CHECK (NEW - Requirement #3)
  │  └─ Redis: cache.get(query, context)
  │     ├─ HIT → Return cached RenderedOutput (fast!)
  │     └─ MISS → Continue to Step 0.75
  │
  ├─ Step 0.75: ⭐ ONTOLOGY VALIDATION (NEW - Requirement #4)
  │  └─ ontology_validator.validate_query_entities(query, entity_refs)
  │     ├─ VALID → Continue
  │     └─ INVALID → Return error RenderedOutput (fail fast)
  │
  ├─ Step 1: NLP Translation (existing)
  ├─ Step 2: Orchestrator (existing)
  ├─ Step 3: Guardrails (existing)
  │
  ├─ Step 3.5: ⭐ TEXT-ONLY CHECK (NEW - Requirement #6)
  │  └─ text_only_detector.should_use_text_only(query)
  │     ├─ YES → Skip Step 4, return text RenderedOutput
  │     └─ NO → Continue to Step 4
  │
  ├─ Step 4: Visualization (existing)
  │  └─ Generate chart/table config
  │
  ├─ Step 5: ⭐ CACHE STORAGE (NEW - Requirement #3)
  │  └─ cache.set(query, context, rendered_output)
  │
  └─ Return RenderedOutput
```

---

## Frontend Component Tree (with new components)

```
ChatInterface
├─ ChatThread
│  └─ ChatMessage[] (role: user, system, error)
│
└─ VisualizationCard[]
   ├─ ChartRenderer (visualizes data)
   │
   ├─ CardToolbar
   │  └─ Dropdown: Visualization Type Selector ✅
   │
   ├─ CardHistoryDropdown ⭐ (NEW - Requirement #2)
   │  ├─ Original Query
   │  ├─ System Response
   │  ├─ Metadata
   │  └─ Column Details
   │
   └─ ConversationStrandSection ⭐ (NEW - Requirement #5, FIXED)
      └─ ConversationStrand (per-strand)
         ├─ Messages[]
         └─ Follow-up Input
```

---

## Store State Structure

### Before
```typescript
SessionState {
  chatThread: ChatMessage[]
  cards: Record<string, CardState>
  strands: Record<string, ConversationStrand>  // Session-only
  ...
}
```

### After (minimal changes)
```typescript
SessionState {
  chatThread: ChatMessage[]
  cards: Record<string, CardState>
  strands: Record<string, ConversationStrand>  // Session remains same
  ...
}
```

**Key Change**: No frontend change needed! Backend caching handles global persistence.

---

## Caching Architecture

### Session Cache (existing)
```
Browser LocalStorage
├─ chatThread
├─ cards
└─ strands
```

### Global Cache (NEW - Requirement #3)
```
Redis Database
├─ Key: cbi:query:{sha256(query + context)}
├─ Value: RenderedOutput (JSON)
└─ TTL: 3600 seconds (configurable)
```

**Advantage**: Same query across different sessions/browsers returns cached result.

---

## Error Handling Flow

### Ontology Validation Error (NEW)
```
Invalid Entity in Query
  ↓
OntologyValidator detects mismatch
  ↓
Returns RenderedOutput with:
  - output_type: "text"
  - text_content: "Entity 'X' not found"
  - metadata: { query_type: "INVALID" }
  ↓
Frontend displays error message
(NO orchestrator/renderer called)
```

### Text-Only Query (NEW)
```
User asks: "summarize the sales data"
  ↓
TextOnlyDetector matches "summarize"
  ↓
Orchestrator retrieves data
  ↓
TextSummaryGenerator creates summary
  ↓
Returns RenderedOutput with:
  - output_type: "text"
  - text_content: summary string
  - chart_data: null
  ↓
Frontend renders text only (no chart)
```

---

## Performance Implications

### Query Latency

**Scenario 1: Cached Query (Global Cache HIT)**
```
Previous: 1200ms (full pipeline)
New:      50ms   (cache lookup + return)
Savings:  1150ms ✅
```

**Scenario 2: First Query (Cache MISS)**
```
Old pipeline:       1200ms
+ Cache check:      +10ms  (Redis ping)
+ Ontology check:   +30ms  (validation)
+ Text detection:   +10ms  (pattern matching)
Total new:          1250ms (only 50ms overhead)
```

**Scenario 3: Invalid Entity (Fail Fast)**
```
Old: Full 1200ms pipeline then error
New: 80ms (Steps 0.75 + return)
Savings: 1120ms ✅
```

---

## Storage Impact

### Redis Memory Estimate
```
Per-query average: 10-50KB (JSON serialized RenderedOutput)
TTL: 1 hour
Capacity: 1000 queries = 10-50MB (typical)
```

**Typical Setup**: 1-5GB Redis instance handles months of queries.

---

## Dependencies Added

```
Backend:
- redis==5.0.1          (for cache_layer.py)

Frontend:
- (none new)
```

---

## Migration Path

### Phase 1: Deploy (Low Risk)
1. Deploy new Python services (cache_layer.py, etc.)
2. Deploy new frontend components
3. Feature flags OFF by default
4. No impact on existing queries

### Phase 2: Enable Cache (Gradual Rollout)
1. Set `ENABLE_QUERY_CACHE=true` (staging)
2. Monitor Redis performance
3. Gradually increase TTL if stable
4. Roll out to production

### Phase 3: Enable Validations (Optional)
1. Set `ENABLE_ONTOLOGY_VALIDATION=true`
2. Set `ENABLE_TEXT_ONLY_DETECTION=true`
3. Monitor error rates
4. Adjust keyword lists if needed

---

## Monitoring & Observability

### Metrics to Track
```
Cache Layer:
- cache_hit_rate (target: 20-40%)
- avg_cache_latency (target: <50ms)
- redis_memory_usage

Ontology Validator:
- validation_fail_rate (target: <5%)
- avg_validation_latency (target: <30ms)

Text Detector:
- text_only_query_rate (target: 10-20%)
- false_positive_rate (target: <2%)
```

### Logging
```python
logger.debug()    # Cache hits/misses
logger.info()     # Validation errors, text detection
logger.warning()  # Redis connection issues
logger.error()    # Critical failures
```

---

## Testing Strategy

### Unit Tests
- `test_cache_layer.py` - Hash consistency, get/set
- `test_ontology_validator.py` - Entity lookup
- `test_text_only_detector.py` - Keyword matching

### Integration Tests
- Full query with cache (hit & miss)
- Ontology error handling
- Text-only response generation

### E2E Tests
- Cached query across sessions
- Conversation strands with follow-ups
- History dropdown display

---

## Backward Compatibility

✅ **Fully Backward Compatible**

- No breaking changes to API contracts
- New components are optional
- Feature flags allow gradual rollout
- Old queries work unchanged
- No frontend state migration needed

---

## Future Enhancements

1. **Advanced Cache** - ML-based query similarity for better cache hits
2. **Distributed Cache** - Multi-region Redis for global deployment
3. **Smart TTL** - Adaptive TTL based on query freshness
4. **Strand Persistence** - Save conversations to database
5. **Analytics** - Query usage patterns & trends

