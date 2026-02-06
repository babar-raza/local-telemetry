#!/bin/bash
# Comprehensive E2E verification of the telemetry API using curl

API_URL="http://localhost:8765"
RESULTS_FILE="e2e_verification_results.txt"
COUNTS_FILE="/tmp/e2e_counts_$$.txt"
UNIQUE_ID=$(date +%s)_$$
EVENT_ID="e2e_test_${UNIQUE_ID}"
RUN_ID="run_${UNIQUE_ID}"

echo "================================================================================" > "$RESULTS_FILE"
echo "TELEMETRY API E2E VERIFICATION" >> "$RESULTS_FILE"
echo "Base URL: $API_URL" >> "$RESULTS_FILE"
echo "Started: $(date -Iseconds)" >> "$RESULTS_FILE"
echo "================================================================================" >> "$RESULTS_FILE"
echo "" >> "$RESULTS_FILE"

# Use file to track counts across subshells
echo "0" > "$COUNTS_FILE.pass"
echo "0" > "$COUNTS_FILE.fail"
echo "0" > "$COUNTS_FILE.time"

test_endpoint() {
    local test_name="$1"
    local method="$2"
    local endpoint="$3"
    local data="$4"
    local expected_status="$5"

    echo "================================================================================"
    echo "$test_name"
    echo "================================================================================"
    echo "$test_name" >> "$RESULTS_FILE"
    echo "Endpoint: $method $endpoint" >> "$RESULTS_FILE"

    local start_time=$(date +%s%N)

    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}\n%{time_total}" -X GET "$API_URL$endpoint")
    elif [ "$method" = "POST" ]; then
        response=$(curl -s -w "\n%{http_code}\n%{time_total}" -X POST "$API_URL$endpoint" \
            -H "Content-Type: application/json" \
            -d "$data")
    elif [ "$method" = "PATCH" ]; then
        response=$(curl -s -w "\n%{http_code}\n%{time_total}" -X PATCH "$API_URL$endpoint" \
            -H "Content-Type: application/json" \
            -d "$data")
    fi

    local end_time=$(date +%s%N)
    local elapsed_ms=$(( (end_time - start_time) / 1000000 ))

    # Update total time
    local current_time=$(cat "$COUNTS_FILE.time")
    echo $((current_time + elapsed_ms)) > "$COUNTS_FILE.time"

    # Extract status code and response time from curl output
    local body=$(echo "$response" | head -n -2)
    local status_code=$(echo "$response" | tail -n 2 | head -n 1)
    local response_time=$(echo "$response" | tail -n 1)

    echo "Status Code: $status_code" >> "$RESULTS_FILE"
    echo "Response Time: ${response_time}s (${elapsed_ms}ms)" >> "$RESULTS_FILE"
    echo "Response Body: $body" >> "$RESULTS_FILE"

    echo "Status Code: $status_code"
    echo "Response Time: ${response_time}s"
    echo "Response: $body"

    if [ "$status_code" = "$expected_status" ]; then
        echo "[PASS]" >> "$RESULTS_FILE"
        echo "[PASS]"
        local pass_count=$(cat "$COUNTS_FILE.pass")
        echo $((pass_count + 1)) > "$COUNTS_FILE.pass"
    else
        echo "[FAIL] Expected status $expected_status, got $status_code" >> "$RESULTS_FILE"
        echo "[FAIL] Expected status $expected_status, got $status_code"
        local fail_count=$(cat "$COUNTS_FILE.fail")
        echo $((fail_count + 1)) > "$COUNTS_FILE.fail"
    fi

    echo "" >> "$RESULTS_FILE"
    echo ""

    # Return the response body for further use
    echo "$body"
}

# Test 1: GET /health
echo "Test 1: GET /health - verify status=ok"
health_response=$(test_endpoint "1. GET /health" "GET" "/health" "" "200")
if echo "$health_response" | grep -q '"status":"ok"' || echo "$health_response" | grep -q '"status": "ok"'; then
    echo "Health check verified: status=ok"
else
    echo "[WARN] Health check failed: status not ok"
fi
echo ""

# Test 2: POST /api/v1/runs - create a test run
echo "Test 2: POST /api/v1/runs - create a test run"
create_payload=$(cat <<EOF
{
  "event_id": "$EVENT_ID",
  "run_id": "$RUN_ID",
  "agent_name": "e2e_test_agent",
  "job_type": "e2e_verification",
  "status": "running",
  "start_time": "$(date -Iseconds)"
}
EOF
)
create_response=$(test_endpoint "2. POST /api/v1/runs" "POST" "/api/v1/runs" "$create_payload" "201")
echo ""

# Test 3: GET /api/v1/runs/{event_id} - retrieve the run
echo "Test 3: GET /api/v1/runs/{event_id} - retrieve the run"
get_response=$(test_endpoint "3. GET /api/v1/runs/{event_id}" "GET" "/api/v1/runs/$EVENT_ID" "" "200")
if echo "$get_response" | grep -q "\"event_id\":\"$EVENT_ID\"" || echo "$get_response" | grep -q "\"event_id\": \"$EVENT_ID\""; then
    echo "Run retrieval verified: event_id matches"
else
    echo "[WARN] Run retrieval failed: event_id mismatch"
fi
echo ""

# Test 4: PATCH /api/v1/runs/{event_id} - update the run
echo "Test 4: PATCH /api/v1/runs/{event_id} - update the run"
update_payload=$(cat <<EOF
{
  "status": "success",
  "end_time": "$(date -Iseconds)",
  "duration_ms": 12345,
  "output_summary": "e2e_patch_test"
}
EOF
)
update_response=$(test_endpoint "4. PATCH /api/v1/runs/{event_id}" "PATCH" "/api/v1/runs/$EVENT_ID" "$update_payload" "200")
echo ""

# Test 5: GET /api/v1/runs - list runs with filters
echo "Test 5: GET /api/v1/runs - list runs with filters"
list_response=$(test_endpoint "5. GET /api/v1/runs" "GET" "/api/v1/runs?agent_name=e2e_test_agent&status=success&limit=10" "" "200")
if echo "$list_response" | grep -q "\"event_id\":\"$EVENT_ID\"" || echo "$list_response" | grep -q "\"event_id\": \"$EVENT_ID\""; then
    echo "List filtering verified: test run found in results"
else
    echo "[WARN] List filtering warning: test run not found in results (may be expected)"
fi
echo ""

# Test 6: POST /api/v1/runs/{event_id}/associate-commit
echo "Test 6: POST /api/v1/runs/{event_id}/associate-commit - associate a git commit"
commit_payload=$(cat <<EOF
{
  "commit_hash": "abc123def456",
  "commit_source": "manual",
  "commit_author": "E2E Test <e2e@test.com>",
  "commit_timestamp": "$(date -Iseconds)"
}
EOF
)
commit_response=$(test_endpoint "6. POST /api/v1/runs/{event_id}/associate-commit" "POST" "/api/v1/runs/$EVENT_ID/associate-commit" "$commit_payload" "200")

# Verify commit fields were stored
echo "Verifying commit fields..."
verify_response=$(curl -s -X GET "$API_URL/api/v1/runs/$EVENT_ID")
echo "Verification response: $verify_response"
if echo "$verify_response" | grep -q '"git_commit_hash":"abc123def456"' || echo "$verify_response" | grep -q '"git_commit_hash": "abc123def456"'; then
    echo "[OK] git_commit_hash verified"
else
    echo "[FAIL] git_commit_hash not found or incorrect"
fi
if echo "$verify_response" | grep -q '"git_commit_source":"manual"' || echo "$verify_response" | grep -q '"git_commit_source": "manual"'; then
    echo "[OK] git_commit_source verified"
else
    echo "[FAIL] git_commit_source not found or incorrect"
fi
if echo "$verify_response" | grep -q '"git_commit_author":"E2E Test <e2e@test.com>"' || echo "$verify_response" | grep -q '"git_commit_author": "E2E Test <e2e@test.com>"'; then
    echo "[OK] git_commit_author verified"
else
    echo "[FAIL] git_commit_author not found or incorrect"
fi
echo ""

# Test 7: GET /api/v1/metadata - get metadata
echo "Test 7: GET /api/v1/metadata - get metadata"
metadata_response=$(test_endpoint "7. GET /api/v1/metadata" "GET" "/api/v1/metadata" "" "200")
if echo "$metadata_response" | grep -q '"agent_names"'; then
    echo "Metadata endpoint verified: agent_names field present"
else
    echo "[WARN] Metadata endpoint warning: agent_names field missing"
fi
echo ""

# Print summary
echo "================================================================================"
echo "SUMMARY"
echo "================================================================================"
echo "================================================================================" >> "$RESULTS_FILE"
echo "SUMMARY" >> "$RESULTS_FILE"
echo "================================================================================" >> "$RESULTS_FILE"

# Read counts from files
PASS_COUNT=$(cat "$COUNTS_FILE.pass")
FAIL_COUNT=$(cat "$COUNTS_FILE.fail")
TOTAL_TIME=$(cat "$COUNTS_FILE.time")

TOTAL_TESTS=$((PASS_COUNT + FAIL_COUNT))

if [ $TOTAL_TESTS -eq 0 ]; then
    SUCCESS_RATE=0
    AVG_TIME=0
else
    SUCCESS_RATE=$(( PASS_COUNT * 100 / TOTAL_TESTS ))
    AVG_TIME=$((TOTAL_TIME / TOTAL_TESTS))
fi

echo "Total Tests: $TOTAL_TESTS" | tee -a "$RESULTS_FILE"
echo "Passed: $PASS_COUNT" | tee -a "$RESULTS_FILE"
echo "Failed: $FAIL_COUNT" | tee -a "$RESULTS_FILE"
echo "Success Rate: ${SUCCESS_RATE}%" | tee -a "$RESULTS_FILE"
echo "" | tee -a "$RESULTS_FILE"

echo "Performance:" | tee -a "$RESULTS_FILE"
echo "  Total Time: ${TOTAL_TIME}ms" | tee -a "$RESULTS_FILE"
echo "  Average Time: ${AVG_TIME}ms" | tee -a "$RESULTS_FILE"
echo "" | tee -a "$RESULTS_FILE"

echo "================================================================================" | tee -a "$RESULTS_FILE"
echo "Completed: $(date -Iseconds)" | tee -a "$RESULTS_FILE"
echo "================================================================================" | tee -a "$RESULTS_FILE"

echo ""
echo "Results saved to: $RESULTS_FILE"

# Cleanup temp files
rm -f "$COUNTS_FILE.pass" "$COUNTS_FILE.fail" "$COUNTS_FILE.time"

if [ $FAIL_COUNT -eq 0 ]; then
    exit 0
else
    exit 1
fi
