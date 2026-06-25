#!/bin/bash

# Test script for Scheduled Reports API
# Tests basic CRUD operations

API_BASE="http://localhost:8005"
USER_ID="test-user-123"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║   Scheduled Reports API Test Suite                        ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Helper function for colored output
print_header() {
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "📋 $1"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Test 1: Health check
print_header "1. Testing Health Endpoint"
curl -X GET "$API_BASE/health" \
  -H "Content-Type: application/json" \
  -w "\nHTTP Status: %{http_code}\n\n"

# Test 2: Create a scheduled report
print_header "2. Creating a Scheduled Report"
CREATE_RESPONSE=$(curl -X POST "$API_BASE/scheduled-reports" \
  -H "Content-Type: application/json" \
  -H "X-User-ID: $USER_ID" \
  -d '{
    "title": "Test Weekly Report",
    "description": "A test scheduled report",
    "original_chat_id": "chat-123-test",
    "pinned_visualization_ids": ["viz-456-test"],
    "recurrence_pattern": {
      "type": "daily",
      "time_hour": 9,
      "time_minute": 0,
      "timezone": "UTC"
    }
  }' \
  -w "\nHTTP Status: %{http_code}\n")

echo "$CREATE_RESPONSE"
REPORT_ID=$(echo "$CREATE_RESPONSE" | grep -o '"report_id":"[^"]*' | head -1 | cut -d'"' -f4)
echo ""
echo "Extracted Report ID: $REPORT_ID"
echo ""

# Test 3: List scheduled reports
print_header "3. Listing All Scheduled Reports"
curl -X GET "$API_BASE/scheduled-reports" \
  -H "Content-Type: application/json" \
  -H "X-User-ID: $USER_ID" \
  -w "\nHTTP Status: %{http_code}\n\n"

# Test 4: Get report details (if we have a report ID)
if [ ! -z "$REPORT_ID" ] && [ "$REPORT_ID" != "null" ]; then
  print_header "4. Getting Report Details"
  curl -X GET "$API_BASE/scheduled-reports/$REPORT_ID" \
    -H "Content-Type: application/json" \
    -H "X-User-ID: $USER_ID" \
    -w "\nHTTP Status: %{http_code}\n\n"

  # Test 5: Update report
  print_header "5. Updating Report"
  curl -X PATCH "$API_BASE/scheduled-reports/$REPORT_ID" \
    -H "Content-Type: application/json" \
    -H "X-User-ID: $USER_ID" \
    -d '{
      "title": "Updated Test Weekly Report"
    }' \
    -w "\nHTTP Status: %{http_code}\n\n"

  # Test 6: Get execution history
  print_header "6. Getting Execution History"
  curl -X GET "$API_BASE/scheduled-reports/$REPORT_ID/executions?page=1&page_size=10" \
    -H "Content-Type: application/json" \
    -H "X-User-ID: $USER_ID" \
    -w "\nHTTP Status: %{http_code}\n\n"

  # Test 7: Pause report
  print_header "7. Pausing Report"
  curl -X POST "$API_BASE/scheduled-reports/$REPORT_ID/pause" \
    -H "Content-Type: application/json" \
    -H "X-User-ID: $USER_ID" \
    -w "\nHTTP Status: %{http_code}\n\n"

  # Test 8: Resume report
  print_header "8. Resuming Report"
  curl -X POST "$API_BASE/scheduled-reports/$REPORT_ID/resume" \
    -H "Content-Type: application/json" \
    -H "X-User-ID: $USER_ID" \
    -w "\nHTTP Status: %{http_code}\n\n"

  # Test 9: Delete report
  print_header "9. Deleting Report"
  curl -X DELETE "$API_BASE/scheduled-reports/$REPORT_ID" \
    -H "Content-Type: application/json" \
    -H "X-User-ID: $USER_ID" \
    -w "\nHTTP Status: %{http_code}\n\n"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║   Test Suite Complete                                      ║"
echo "╚════════════════════════════════════════════════════════════╝"
