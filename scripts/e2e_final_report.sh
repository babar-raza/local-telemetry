#!/bin/bash
# Final E2E verification report for telemetry API

API_URL="http://localhost:8765"
UNIQUE_ID=$(date +%s)_$$
EVENT_ID="e2e_final_${UNIQUE_ID}"
RUN_ID="run_${UNIQUE_ID}"

echo "================================================================================"
echo "TELEMETRY API E2E VERIFICATION - FINAL REPORT"
echo "Base URL: $API_URL"
echo "Test Run ID: $EVENT_ID"
echo "Started: $(date -Iseconds)"
echo "================================================================================"
echo ""

# Test 1: GET /health
echo "================================================================================"
echo "TEST 1: GET /health"
echo "================================================================================"
response=$(curl -s -w "\n%{http_code}" "$API_URL/health")
body=$(echo "$response" | head -n -1)
status=$(echo "$response" | tail -n 1)
echo "Status Code: $status"
echo "Response: $body"
if [ "$status" = "200" ] && echo "$body" | grep -q '"status":"ok"'; then
    echo "Result: ✓ PASS - Health check successful, status=ok"
    TEST1="PASS"
else
    echo "Result: ✗ FAIL - Health check failed"
    TEST1="FAIL"
fi
echo ""

# Test 2: POST /api/v1/runs
echo "================================================================================"
echo "TEST 2: POST /api/v1/runs - Create test run"
echo "================================================================================"
payload=$(cat <<EOF
{
  "event_id": "$EVENT_ID",
  "run_id": "$RUN_ID",
  "agent_name": "e2e_final_test",
  "job_type": "e2e_verification",
  "status": "running",
  "start_time": "$(date -Iseconds)"
}
EOF
)
echo "Payload: $payload"
response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/api/v1/runs" \
    -H "Content-Type: application/json" \
    -d "$payload")
body=$(echo "$response" | head -n -1)
status=$(echo "$response" | tail -n 1)
echo "Status Code: $status"
echo "Response: $body"
if [ "$status" = "201" ] && echo "$body" | grep -q '"status":"created"'; then
    echo "Result: ✓ PASS - Run created successfully"
    TEST2="PASS"
else
    echo "Result: ✗ FAIL - Run creation failed"
    TEST2="FAIL"
fi
echo ""

# Test 3: GET /api/v1/runs/{event_id}
echo "================================================================================"
echo "TEST 3: GET /api/v1/runs/{event_id} - Retrieve run"
echo "================================================================================"
response=$(curl -s -w "\n%{http_code}" "$API_URL/api/v1/runs/$EVENT_ID")
body=$(echo "$response" | head -n -1)
status=$(echo "$response" | tail -n 1)
echo "Status Code: $status"
echo "Response: $body"
if [ "$status" = "200" ] && echo "$body" | grep -q "\"event_id\":\"$EVENT_ID\""; then
    echo "Result: ✓ PASS - Run retrieved successfully, event_id matches"
    TEST3="PASS"
else
    echo "Result: ✗ FAIL - Run retrieval failed"
    TEST3="FAIL"
fi
echo ""

# Test 4: PATCH /api/v1/runs/{event_id}
echo "================================================================================"
echo "TEST 4: PATCH /api/v1/runs/{event_id} - Update run"
echo "================================================================================"
update_payload=$(cat <<EOF
{
  "status": "success",
  "end_time": "$(date -Iseconds)",
  "duration_ms": 12345,
  "output_summary": "E2E test completed"
}
EOF
)
echo "Payload: $update_payload"
response=$(curl -s -w "\n%{http_code}" -X PATCH "$API_URL/api/v1/runs/$EVENT_ID" \
    -H "Content-Type: application/json" \
    -d "$update_payload")
body=$(echo "$response" | head -n -1)
status=$(echo "$response" | tail -n 1)
echo "Status Code: $status"
echo "Response: $body"
if [ "$status" = "200" ] && echo "$body" | grep -q '"updated":true'; then
    echo "Result: ✓ PASS - Run updated successfully"
    TEST4="PASS"
else
    echo "Result: ✗ FAIL - Run update failed"
    TEST4="FAIL"
fi
echo ""

# Test 5: GET /api/v1/runs - List runs with filters
echo "================================================================================"
echo "TEST 5: GET /api/v1/runs - List runs with filters"
echo "================================================================================"
response=$(curl -s -w "\n%{http_code}" "$API_URL/api/v1/runs?agent_name=e2e_final_test&status=success&limit=10")
body=$(echo "$response" | head -n -1)
status=$(echo "$response" | tail -n 1)
echo "Status Code: $status"
echo "Response: $body" | head -c 500
echo "... (truncated)"
if [ "$status" = "200" ] && echo "$body" | grep -q "\"event_id\":\"$EVENT_ID\""; then
    echo "Result: ✓ PASS - List returned successfully, test run found in filtered results"
    TEST5="PASS"
else
    echo "Result: ✗ FAIL - List filtering failed"
    TEST5="FAIL"
fi
echo ""

# Test 6: POST /api/v1/runs/{event_id}/associate-commit
echo "================================================================================"
echo "TEST 6: POST /api/v1/runs/{event_id}/associate-commit"
echo "================================================================================"
commit_payload=$(cat <<EOF
{
  "commit_hash": "abc123def456",
  "commit_source": "manual",
  "commit_author": "E2E Test <e2e@test.com>",
  "commit_timestamp": "$(date -Iseconds)"
}
EOF
)
echo "Payload: $commit_payload"
response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/api/v1/runs/$EVENT_ID/associate-commit" \
    -H "Content-Type: application/json" \
    -d "$commit_payload")
body=$(echo "$response" | head -n -1)
status=$(echo "$response" | tail -n 1)
echo "Status Code: $status"
echo "Response: $body"

if [ "$status" = "200" ]; then
    echo "Result: ✓ PASS - Commit association successful"
    TEST6="PASS"

    # Verify commit fields in database
    echo ""
    echo "Verifying commit fields were stored..."
    verify_response=$(curl -s "$API_URL/api/v1/runs/$EVENT_ID")
    echo "Verification response (commit fields):"
    echo "$verify_response" | grep -o '"git_commit[^"]*":[^,}]*' || echo "No git_commit fields found"

    if echo "$verify_response" | grep -q '"git_commit_hash":"abc123def456"'; then
        echo "✓ git_commit_hash correctly stored"
    else
        echo "✗ git_commit_hash NOT stored correctly"
    fi

    if echo "$verify_response" | grep -q '"git_commit_source":"manual"'; then
        echo "✓ git_commit_source correctly stored"
    else
        echo "✗ git_commit_source NOT stored correctly"
    fi

    if echo "$verify_response" | grep -q '"git_commit_author":"E2E Test <e2e@test.com>"'; then
        echo "✓ git_commit_author correctly stored"
    else
        echo "✗ git_commit_author NOT stored correctly"
    fi
elif [ "$status" = "500" ] && echo "$body" | grep -q "no such column: updated_at"; then
    echo "Result: ✗ FAIL - Database error: missing 'updated_at' column"
    echo "ERROR: The API code references 'updated_at' column which doesn't exist in schema"
    echo "       This is a bug in telemetry_service.py line 1499"
    TEST6="FAIL"
else
    echo "Result: ✗ FAIL - Commit association failed"
    TEST6="FAIL"
fi
echo ""

# Test 7: GET /api/v1/runs/count
echo "================================================================================"
echo "TEST 7: GET /api/v1/runs/count (EXPECTED TO FAIL - endpoint doesn't exist)"
echo "================================================================================"
response=$(curl -s -w "\n%{http_code}" "$API_URL/api/v1/runs/count?agent_name=e2e_final_test&status=success")
body=$(echo "$response" | head -n -1)
status=$(echo "$response" | tail -n 1)
echo "Status Code: $status"
echo "Response: $body"
if [ "$status" = "404" ]; then
    echo "Result: ✗ FAIL (EXPECTED) - Endpoint /api/v1/runs/count does not exist"
    echo "NOTE: This endpoint was requested in the test requirements but is not implemented"
    TEST7="FAIL (Expected)"
else
    echo "Result: Unexpected response"
    TEST7="FAIL"
fi
echo ""

# Test 8: GET /api/v1/stats
echo "================================================================================"
echo "TEST 8: GET /api/v1/stats (EXPECTED TO FAIL - endpoint doesn't exist)"
echo "================================================================================"
response=$(curl -s -w "\n%{http_code}" "$API_URL/api/v1/stats")
body=$(echo "$response" | head -n -1)
status=$(echo "$response" | tail -n 1)
echo "Status Code: $status"
echo "Response: $body"
if [ "$status" = "404" ]; then
    echo "Result: ✗ FAIL (EXPECTED) - Endpoint /api/v1/stats does not exist"
    echo "NOTE: This endpoint was requested in the test requirements but is not implemented"
    TEST8="FAIL (Expected)"
else
    echo "Result: Unexpected response"
    TEST8="FAIL"
fi
echo ""

# BONUS: Test /api/v1/metadata (since stats/count don't exist)
echo "================================================================================"
echo "BONUS TEST: GET /api/v1/metadata"
echo "================================================================================"
echo "NOTE: Testing this as an alternative since /stats and /count don't exist"
echo "WARNING: This endpoint can be slow with large datasets (21M rows)"
response=$(curl -s -w "\n%{http_code}" "$API_URL/api/v1/metadata?limit=5")
body=$(echo "$response" | head -n -1)
status=$(echo "$response" | tail -n 1)
echo "Status Code: $status"
echo "Response: $body" | head -c 500
echo "... (truncated)"
if [ "$status" = "200" ]; then
    echo "Result: ✓ PASS - Metadata endpoint working"
    BONUS="PASS"
else
    echo "Result: ✗ FAIL - Metadata endpoint failed"
    BONUS="FAIL"
fi
echo ""

# Summary
echo "================================================================================"
echo "FINAL SUMMARY"
echo "================================================================================"
echo ""
echo "Core Endpoints (Required):"
echo "  1. GET /health                                    : $TEST1"
echo "  2. POST /api/v1/runs                              : $TEST2"
echo "  3. GET /api/v1/runs/{event_id}                    : $TEST3"
echo "  4. PATCH /api/v1/runs/{event_id}                  : $TEST4"
echo "  5. GET /api/v1/runs (with filters)                : $TEST5"
echo "  6. POST /api/v1/runs/{event_id}/associate-commit  : $TEST6"
echo ""
echo "Requested Endpoints (Not Implemented):"
echo "  7. GET /api/v1/runs/count                         : $TEST7"
echo "  8. GET /api/v1/stats                              : $TEST8"
echo ""
echo "Alternative Endpoints:"
echo "  Bonus: GET /api/v1/metadata                       : $BONUS"
echo ""

# Count results
CORE_PASS=0
[ "$TEST1" = "PASS" ] && CORE_PASS=$((CORE_PASS + 1))
[ "$TEST2" = "PASS" ] && CORE_PASS=$((CORE_PASS + 1))
[ "$TEST3" = "PASS" ] && CORE_PASS=$((CORE_PASS + 1))
[ "$TEST4" = "PASS" ] && CORE_PASS=$((CORE_PASS + 1))
[ "$TEST5" = "PASS" ] && CORE_PASS=$((CORE_PASS + 1))
[ "$TEST6" = "PASS" ] && CORE_PASS=$((CORE_PASS + 1))

echo "Core Endpoint Results: $CORE_PASS / 6 PASSED"
echo ""

if [ "$TEST6" = "FAIL" ]; then
    echo "CRITICAL ISSUE FOUND:"
    echo "  - Test 6 (associate-commit) failed due to database schema mismatch"
    echo "  - The API code tries to update 'updated_at' column which doesn't exist"
    echo "  - Location: telemetry_service.py, line 1499"
    echo "  - Fix required: Remove 'updated_at' field from UPDATE query or add column to schema"
    echo ""
fi

echo "MISSING ENDPOINTS:"
echo "  - /api/v1/runs/count - Not implemented"
echo "  - /api/v1/stats - Not implemented"
echo "  - Alternative: /api/v1/metadata exists but can be very slow (21M rows)"
echo ""

echo "================================================================================"
echo "Completed: $(date -Iseconds)"
echo "================================================================================"
