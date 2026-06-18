#!/usr/bin/env python
"""Test script to submit a query and check the response."""

import json
import httpx

# Test the NLP translator
print("Testing NLP Translator endpoint...")
query_text = "How many employees are remote vs in-office"
payload = {"query_text": query_text}

try:
    response = httpx.post(
        "http://localhost:8001/query",
        json=payload,
        timeout=30.0
    )
    print(f"Status: {response.status_code}")
    result = response.json()
    print(f"Response:\n{json.dumps(result, indent=2)}")
except Exception as e:
    print(f"Error: {e}")

# Also test orchestrator
print("\n" + "="*60)
print("Testing Orchestrator Hub endpoint...")
payload = {"query_text": query_text}

try:
    response = httpx.post(
        "http://localhost:8002/internal/process",
        json=payload,
        timeout=60.0
    )
    print(f"Status: {response.status_code}")
    result = response.json()
    print(f"Response:\n{json.dumps(result, indent=2)}")
except Exception as e:
    print(f"Error: {e}")
