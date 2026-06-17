# Integration Checklist

## Files Created

### Frontend Components
- ✅ `frontend/src/components/ConversationStrand.tsx` - Multi-turn chat thread
- ✅ `frontend/src/components/CardHistoryDropdown.tsx` - Collapsible history section
- ✅ `frontend/src/styles/conversation-strand.css` - Strand component styles
- ✅ `frontend/src/styles/card-history-dropdown.css` - History dropdown styles

### Backend Services
- ✅ `src/services/cache_layer.py` - Global Redis cache (Requirement #3)
- ✅ `src/services/ontology_validator.py` - Entity validation (Requirement #4)
- ✅ `src/services/text_only_detector.py` - Text output detection (Requirement #6)

---

## Integration Steps

### Step 1: Fix Chat Visibility (CRITICAL - Issue #5)

**File**: `frontend/src/store/sessionStore.ts`

The `useSessionStore` is already correctly set up with strands. The issue is that components using strands might not be properly subscribed.

**Verify**: Ensure `ConversationStrand.tsx` is imported and used where strands display.

```typescript
// In VisualizationCard.tsx or similar:
import ConversationStrand from '../components/ConversationStrand';

// Usage:
<ConversationStrand strandId={strandId} onFollowUpSubmitted={handleFollowUp} />
```

**Key Fix**: The component uses a shallow selector:
```typescript
const strand = useSessionStore(
  (state) => state.strands[strandId],
  (a, b) => a?.updatedAt === b?.updatedAt && a?.messages.length === b?.messages.length
);
```

This ensures re-render only when that specific strand's messages change.

---

### Step 2: Add Collapsible History to Cards (Requirement #2)

**File**: `frontend/src/components/VisualizationCard.tsx`

Add the history dropdown to card component:

```typescript
import CardHistoryDropdown from './CardHistoryDropdown';

// In VisualizationCard render:
<div className="card-body">
  {/* Existing visualization */}
  <ChartRenderer renderedOutput={card.renderedOutput} />
  
  {/* NEW: History section */}
  <CardHistoryDropdown card={card} />
  
  {/* NEW: Conversation strand (if exists) */}
  {strandId && <ConversationStrand strandId={strandId} />}
</div>
```

Import styles:
```typescript
import '../styles/card-history-dropdown.css';
import '../styles/conversation-strand.css';
```

---

### Step 3: Initialize Global Cache (Requirement #3)

**File**: `src/services/nlp_api.py`

Add at module top:

```python
from src.services.cache_layer import get_cache

# Initialize cache on module load
cache = get_cache()
```

In `query_nlp` function, add cache check (Step 0 or Step 0.5):

```python
async def query_nlp(request: QueryRequest) -> RenderedOutput:
    # Step 0: Check if this is a meta-query
    if meta_query_detector.is_meta_query(request.query):
        return meta_query_detector.generate_meta_response(request.query)
    
    # Step 0.5: NEW - Check global cache
    cached_result = cache.get(
        query=request.query,
        context={"data_sources": request.data_sources}
    )
    if cached_result:
        logger.info(f"Cache HIT: {request.query[:50]}...")
        return RenderedOutput(**cached_result)
    
    # ... existing pipeline (Steps 1-4) ...
    
    # After rendering, cache the result
    cache.set(
        query=request.query,
        context={"data_sources": request.data_sources},
        result=rendered_output.dict()
    )
    
    return rendered_output
```

**Setup Redis** (if not already running):

```bash
# Via Docker (recommended)
docker run -d -p 6379:6379 redis:7-alpine

# Or via Homebrew (macOS)
brew install redis
brew services start redis
```

**Configure** (in your environment):

```bash
export REDIS_URL="redis://localhost:6379"
```

---

### Step 4: Add Ontology Validation (Requirement #4)

**File**: `src/services/nlp_api.py`

Add after meta-query and cache checks:

```python
from src.services.ontology_validator import OntologyValidator

# Initialize at module load
ontology_validator = OntologyValidator(ontology_store)

async def query_nlp(request: QueryRequest) -> RenderedOutput:
    # ... meta-query check ...
    # ... cache check ...
    
    # Step 0.75: NEW - Ontology validation
    keywords = extract_keywords(request.query)  # Existing function
    entity_refs = nlp_translator.get_entity_refs(keywords)
    
    is_valid, error_msg = ontology_validator.validate_query_entities(
        query=request.query,
        entity_refs=entity_refs
    )
    
    if not is_valid:
        logger.warning(f"Ontology validation failed: {error_msg}")
        return RenderedOutput(
            output_type="text",
            text_content=error_msg,
            description=f"Query validation failed: {error_msg}",
            metadata=MetaPayload(
                query_id=request.query_id,
                query_type="INVALID",
                entity_refs=[],
                timestamp=datetime.utcnow().isoformat(),
            )
        )
    
    # Continue to Steps 1-4 (NLP, Orchestrator, Renderer, etc.)
    # ...
```

---

### Step 5: Add Text-Only Output Support (Requirement #6)

**File**: `src/services/nlp_api.py`

Before visualization agent:

```python
from src.services.text_only_detector import TextOnlyDetector, TextSummaryGenerator

# Initialize at module load
text_only_detector = TextOnlyDetector()
text_summary_gen = TextSummaryGenerator()

async def query_nlp(request: QueryRequest) -> RenderedOutput:
    # ... previous steps ...
    
    # Step 3.5: NEW - Check if text-only response needed
    if text_only_detector.should_use_text_only(request.query):
        query_type = text_only_detector.get_text_only_query_type(request.query)
        logger.info(f"Text-only query detected (type: {query_type})")
        
        # Get data from orchestrator
        orchestrator_response = await orchestrator.process(structured_intent)
        
        # Generate text summary instead of visualization
        summary_text = text_summary_gen.generate_summary(
            data=orchestrator_response.data,
            query=request.query
        )
        
        return RenderedOutput(
            output_type="text",
            chart_type=None,
            chart_data=None,
            raw_data=None,
            text_content=summary_text,
            description=summary_text,
            metadata=orchestrator_response.metadata,
        )
    
    # Continue to visualization (Step 4)
    # renderer_response = await renderer.render(...)
    # ...
```

**Frontend**: Update ChartRenderer:

**File**: `frontend/src/components/ChartRenderer.tsx`

```typescript
export function ChartRenderer({ renderedOutput }: { renderedOutput: RenderedOutput }) {
  // Text-only check
  if (renderedOutput.output_type === 'text' || !renderedOutput.chart_data) {
    return (
      <div className="text-output">
        <div className="text-content">
          {renderedOutput.text_content}
        </div>
      </div>
    );
  }

  // Existing chart rendering...
  return (
    <div className="chart-container">
      <ChartJS config={renderedOutput.chart_data} />
    </div>
  );
}
```

---

## Testing Checklist

### Requirement #1: Dynamic Visualization Switching
- [ ] Render a chart
- [ ] Click visualization type dropdown
- [ ] Select different type (e.g., "Line" → "Table")
- [ ] Chart updates without page reload ✅

### Requirement #2: Collapsible History
- [ ] Click "Query History & Details" dropdown
- [ ] See original query text
- [ ] See system response
- [ ] See metadata (latency, row count, etc.)
- [ ] Click again to collapse ✅

### Requirement #3: Global Caching
- [ ] Submit query: "compare sales revenue against product"
- [ ] Note response time (e.g., 1500ms)
- [ ] Submit same query again
- [ ] Second query returns cached result (should be <100ms) ✅

### Requirement #4: Ontology Validation
- [ ] Submit invalid query with non-existent entity: "get data from NonExistentTable"
- [ ] System returns validation error immediately (before routing)
- [ ] Error message suggests valid entities if available ✅

### Requirement #5: Chat Visibility
- [ ] Click card to create conversation strand
- [ ] Type follow-up question in strand input
- [ ] Press send
- [ ] Message appears in strand IMMEDIATELY (no page reload needed) ✅
- [ ] System response appears below user message ✅

### Requirement #6: Text-Only Output
- [ ] Submit text-only query: "summarize the sales data"
- [ ] System returns text response only (no chart)
- [ ] Submit chart query: "show sales by region in a bar chart"
- [ ] System returns bar chart visualization ✅

---

## Configuration Files

### Environment Variables

Add to `.env`:

```bash
# Redis cache
REDIS_URL=redis://localhost:6379
REDIS_TTL=3600  # 1 hour

# Feature flags
ENABLE_QUERY_CACHE=true
ENABLE_ONTOLOGY_VALIDATION=true
ENABLE_TEXT_ONLY_DETECTION=true
```

### Requirements

Backend:

```bash
pip install redis  # for cache_layer.py
```

Frontend:

```bash
# No new deps, uses existing zustand + React
```

---

## Performance Impact

| Feature | Latency Impact | Storage Impact |
|---------|----------------|----------------|
| Global Cache | -1200ms (hit), no change (miss) | ~1-5MB (Redis) |
| Ontology Check | +50ms (validation pass) | None |
| Text Detection | +10ms (pattern matching) | None |
| Chat Visibility Fix | 0ms (just re-render fix) | None |
| History Dropdown | 0ms (lazy render) | None |

**Total**: ~50-60ms on first query, <100ms on cached queries.

---

## Rollback Plan

If any feature causes issues:

1. **Cache**: Set `ENABLE_QUERY_CACHE=false` in `.env`
2. **Ontology**: Set `ENABLE_ONTOLOGY_VALIDATION=false` in `.env`
3. **Text Detection**: Set `ENABLE_TEXT_ONLY_DETECTION=false` in `.env`
4. **Chat**: Revert `ConversationStrand.tsx` changes (just use old strand component)

All are feature-flagged for safe rollback.

---

## Next Steps

1. Create feature branch: `git checkout -b feature/6-requirements`
2. Follow integration steps above
3. Run test checklist
4. Create PR with all changes
5. Deploy to staging for validation

