# Feature Enhancement Implementation Guide

## Overview
Six critical improvements to the Conversational BI chat interface:
1. Dynamic visualization type switching
2. Collapsible chat history in card
3. Global vs session-based caching
4. Ontology checks in card query
5. Dynamic chat visibility issue fix
6. Text-only output support

---

## Issue #5: Chat Not Visible After First Message (CRITICAL)

### Root Cause
The `submitFollowUpQuery` action adds messages to `strand.messages`, but the component listening to strands is not re-rendering. This is likely because:

1. **Strand updates not triggering subscriptions** - The component may not be watching the right store selector
2. **Stale closure** - Event handlers capturing old strand state
3. **Component not re-rendering on message arrival** - Missing dependency in useEffect

### Solution - Fix Strand Component

**File**: `frontend/src/components/ConversationStrand.tsx` (create if doesn't exist)

```typescript
import React, { useEffect, useState } from 'react';
import { useSessionStore } from '../store/sessionStore';
import type { ConversationStrand, ChatMessage } from '../types';

export function ConversationStrand({ strandId }: { strandId: string }) {
  const strand = useSessionStore((state) => state.strands[strandId]);
  const loading = useSessionStore((state) => state.loading);
  const submitFollowUp = useSessionStore((state) => state.submitFollowUpQuery);
  
  const [followUpText, setFollowUpText] = useState('');

  if (!strand) {
    return <div>Strand not found</div>;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!followUpText.trim()) return;

    // ✅ CRITICAL: Clear input BEFORE async call to prevent stale state
    const query = followUpText;
    setFollowUpText('');

    // ✅ CRITICAL: Use strandId from props, not from closure
    await submitFollowUp(strandId, query);
  };

  return (
    <div className="strand-container">
      {/* ✅ CRITICAL: Use shallow selector to watch only this strand */}
      <div className="messages">
        {strand.messages.map((msg) => (
          <div key={msg.id} className={`message ${msg.role}`}>
            {msg.content}
          </div>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="follow-up-form">
        <input
          type="text"
          value={followUpText}
          onChange={(e) => setFollowUpText(e.target.value)}
          placeholder="Ask a follow-up question..."
          disabled={loading}
        />
        <button type="submit" disabled={loading}>
          Send
        </button>
      </form>
    </div>
  );
}
```

**Key Fixes**:
- ✅ Selector targets exact strand: `state.strands[strandId]` (not all strands)
- ✅ Clear input BEFORE async call (prevents stale closure)
- ✅ Use strandId from props (not closure)
- ✅ Component re-renders when strand.messages changes

---

## Issue #1: Dynamic Visualization Type Switching ✅ (ALREADY IMPLEMENTED)

Your `CardToolbar.tsx` already handles this. Verify it's working:

**File**: `frontend/src/components/CardToolbar.tsx`

The implementation is correct. Just ensure:
1. Dropdown sends correct `newType`
2. `changeCardVisualizationType` updates state
3. ChartRenderer reads `selectedVisualizationType` and re-renders

---

## Issue #2: Collapsible Chat History in Card

### Design
Add an "expandable history" section to the card that shows previous messages in an accordion.

**File**: `frontend/src/components/VisualizationCard.tsx` (add section)

```typescript
import { useState } from 'react';
import type { CardState } from '../types';

interface VisualizationCardProps {
  card: CardState;
  onCreateStrand?: (cardId: string) => void;
}

export function VisualizationCard({ card, onCreateStrand }: VisualizationCardProps) {
  const [showHistory, setShowHistory] = useState(false);

  return (
    <div className="card">
      {/* Existing visualization */}
      <div className="card-content">
        {/* Chart/Text renderer here */}
      </div>

      {/* ✅ NEW: Collapsible history section */}
      <div className="card-history-section">
        <button
          className="history-toggle"
          onClick={() => setShowHistory(!showHistory)}
          aria-expanded={showHistory}
        >
          <ChevronIcon />
          <span>Chat History ({card.query.length})</span>
        </button>

        {showHistory && (
          <div className="history-dropdown">
            <div className="history-content">
              <p className="original-query">
                <strong>Original Query:</strong>
                <br />
                {card.query}
              </p>

              <div className="description">
                <strong>System Response:</strong>
                <br />
                {card.renderedOutput.description}
              </div>

              {/* Show metadata if present */}
              {card.renderedOutput.metadata && (
                <details className="metadata-details">
                  <summary>Metadata</summary>
                  <pre>{JSON.stringify(card.renderedOutput.metadata, null, 2)}</pre>
                </details>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Strand conversation section */}
      {card.id && (
        <ConversationStrandSection
          cardId={card.id}
          onCreateStrand={onCreateStrand}
        />
      )}
    </div>
  );
}

function ConversationStrandSection({
  cardId,
  onCreateStrand,
}: {
  cardId: string;
  onCreateStrand?: (cardId: string) => void;
}) {
  const [strandId, setStrandId] = useState<string | null>(null);
  const strands = useSessionStore((state) => state.strands);

  const handleCreateStrand = () => {
    const { createStrand } = useSessionStore((state) => ({
      createStrand: state.createStrand,
    }));
    const newStrandId = createStrand(cardId);
    setStrandId(newStrandId);
    onCreateStrand?.(cardId);
  };

  if (!strandId) {
    return (
      <button onClick={handleCreateStrand} className="start-conversation-btn">
        💬 Start Conversation
      </button>
    );
  }

  return <ConversationStrand strandId={strandId} />;
}
```

**CSS**:

```css
.card-history-section {
  border-top: 1px solid #e5e7eb;
  margin-top: 1rem;
  padding-top: 1rem;
}

.history-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: none;
  border: none;
  cursor: pointer;
  font-weight: 500;
  color: #374151;
  padding: 0.5rem;
}

.history-toggle:hover {
  color: #1f2937;
}

.history-dropdown {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 0.375rem;
  margin-top: 0.5rem;
  padding: 1rem;
  max-height: 300px;
  overflow-y: auto;
}

.original-query {
  font-size: 0.875rem;
  line-height: 1.5;
  color: #1f2937;
  margin-bottom: 1rem;
}

.metadata-details {
  margin-top: 0.5rem;
  font-size: 0.75rem;
  color: #6b7280;
}

.metadata-details pre {
  background: white;
  border: 1px solid #d1d5db;
  border-radius: 0.25rem;
  padding: 0.5rem;
  overflow-x: auto;
  font-size: 0.7rem;
}
```

---

## Issue #3: Global vs Session-Based Caching

### Design
Move from localStorage (per-session) to **Redis backend cache** (global, per-query hash).

**Backend Implementation**:

**File**: `src/services/cache_layer.py` (create)

```python
import hashlib
import json
from typing import Optional, Any
import redis

class GlobalQueryCache:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.ttl = 3600  # 1 hour TTL for cache entries

    def _hash_query(self, query: str, context: dict) -> str:
        """Hash query + context into cache key."""
        combined = json.dumps({"query": query, "context": context}, sort_keys=True)
        return hashlib.sha256(combined.encode()).hexdigest()

    def get(self, query: str, context: dict) -> Optional[Any]:
        """Retrieve cached result if exists."""
        cache_key = f"cbi:query:{self._hash_query(query, context)}"
        cached = self.redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
        return None

    def set(self, query: str, context: dict, result: Any) -> None:
        """Store query result in global cache."""
        cache_key = f"cbi:query:{self._hash_query(query, context)}"
        self.redis_client.setex(
            cache_key,
            self.ttl,
            json.dumps(result, default=str),
        )

    def clear(self) -> None:
        """Clear all CBI cache entries."""
        for key in self.redis_client.scan_iter("cbi:query:*"):
            self.redis_client.delete(key)
```

**Integration**:

**File**: `src/services/nlp_api.py` (modify)

```python
from src.services.cache_layer import GlobalQueryCache

cache = GlobalQueryCache()

async def query_nlp(request: QueryRequest) -> RenderedOutput:
    # ✅ NEW: Check global cache FIRST
    cached_result = cache.get(
        query=request.query,
        context={"data_sources": request.data_sources}
    )
    if cached_result:
        return RenderedOutput(**cached_result)

    # ... rest of pipeline ...

    # ✅ NEW: Cache the result globally
    cache.set(
        query=request.query,
        context={"data_sources": request.data_sources},
        result=rendered_output.dict()
    )

    return rendered_output
```

**Frontend Change**: Remove localStorage for raw_data; rely on server cache.

---

## Issue #4: Ontology Check in Card Query

### Design
Add ontology validation as a **pre-flight check** in the card query handler, not as separate step.

**Backend**:

**File**: `src/services/ontology_validator.py` (create)

```python
from src.data.ontology_store import OntologyStore
from typing import List, Tuple

class OntologyValidator:
    def __init__(self, ontology: OntologyStore):
        self.ontology = ontology

    def validate_query_entities(self, query: str, entity_refs: List[str]) -> Tuple[bool, Optional[str]]:
        """
        Check if all entities in the query are valid ontology entities.
        Returns (is_valid, error_message)
        """
        for entity_ref in entity_refs:
            if not self.ontology.entity_exists(entity_ref):
                return False, f"Entity '{entity_ref}' not found in ontology"

        return True, None
```

**Integration**:

**File**: `src/services/nlp_api.py` (add step)

```python
# Step 0.5: Ontology validation (after meta-query check)
is_valid, error_msg = ontology_validator.validate_query_entities(
    query=request.query,
    entity_refs=extracted_entities
)

if not is_valid:
    return RenderedOutput(
        output_type="text",
        text_content=error_msg,
        description=f"Query validation failed: {error_msg}",
        metadata=MetaPayload(
            query_id=request.query_id,
            query_type="INVALID",
            entity_refs=[],
        )
    )
```

---

## Issue #6: Text-Only Output Support (NO ARCHITECTURE CHANGE NEEDED)

### Solution
Modify visualization agent to detect text-only queries and return `raw_data: null`.

**File**: `src/services/visualization_agent.py` (modify)

```python
def should_use_visualization(query: str, data: Any) -> bool:
    """Determine if query requires visualization or text-only response."""
    text_only_keywords = [
        "explain", "what is", "describe", "summarize",
        "how many", "count", "total", "list",
    ]

    query_lower = query.lower()
    return not any(kw in query_lower for kw in text_only_keywords)

async def visualize_data(query: str, data: Any) -> RenderedOutput:
    if not should_use_visualization(query, data):
        # ✅ Return text-only output
        return RenderedOutput(
            output_type="text",
            chart_type=None,
            chart_data=None,
            raw_data=None,
            text_content=generate_summary_text(data),
            description="Text response",
            metadata=...
        )

    # ... existing visualization logic ...
```

**Frontend**:

**File**: `frontend/src/components/ChartRenderer.tsx` (modify)

```typescript
export function ChartRenderer({ renderedOutput }: { renderedOutput: RenderedOutput }) {
  // ✅ If no chart data, render text only
  if (!renderedOutput.chart_data || renderedOutput.output_type === 'text') {
    return (
      <div className="text-output">
        {renderedOutput.text_content}
      </div>
    );
  }

  // ... existing chart rendering ...
}
```

---

## Summary of Changes

| Issue | Type | Impact | Architecture Change? |
|-------|------|--------|----------------------|
| #1: Viz Switching | ✅ Done | UI/UX | No |
| #2: Collapsible History | Feature | UI/UX | No |
| #3: Global Cache | Optimization | Backend | Yes (add Redis) |
| #4: Ontology Check | Validation | Backend | No (reorder steps) |
| #5: Chat Visibility | 🔴 **Bug** | **Critical** | **No (just fix selector)** |
| #6: Text-Only Output | Feature | Backend/Frontend | **No (keyword detection)** |

---

## Implementation Priority

1. **🔴 CRITICAL**: Fix #5 (chat visibility) - Affects core functionality
2. **High**: Fix #2 (collapsible history) - UX improvement
3. **Medium**: Implement #3 (global cache) - Performance optimization
4. **Medium**: Implement #6 (text-only output) - Feature completeness
5. **Low**: Implement #4 (ontology check) - Validation hardening

---

## Testing Checklist

- [ ] Issue #5: Submit follow-up → Messages appear immediately without reload
- [ ] Issue #2: Click history dropdown → Shows query + response + metadata
- [ ] Issue #3: Cache same query twice → Second query returns cached result
- [ ] Issue #4: Invalid entity in query → Returns error before orchestrator
- [ ] Issue #6: Text-heavy query (e.g., "summarize") → Returns text, no chart

