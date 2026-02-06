#!/bin/bash
# Quick E2E verification (skips slow metadata endpoint)

API_URL="http://localhost:8765"
UNIQUE_ID=$(date +%s)_$$
EVENT_ID="e2e_quick_${UNIQUE_ID}"
RUN_ID="run_quick_${UNIQUE_ID}"

echo "================================================================================"
echo "QUICK E2E VERIFICATION"
echo "================================================================================"

PASS_COUNT=0
FAIL_COUNT=0

test_pass() {
    echo "[PASS] $1"
    PASS_COUNT=$((PASS_COUNT + 1))
}

test_fail() {
    echo "[FAIL] $1"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

# Test 1: Health check
echo ""
echo "Test 1: GET /health"
response=$(curl -s -w "%{http_code}" -X GET "$API_URL/health")
status_code="${response:(-3)}"
body="${response:0:-3}"
if [ "$status_code" = "200" ] && echo "$body" | grep -q '"status":"ok"'; then
    test_pass "Health endpoint working"
else
    test_fail "Health endpoint failed (status=$status_code)"
fi

# Test 2: Create run
echo ""
echo "Test 2: POST /api/v1/runs"
response=$(curl -s -w "%{http_code}" -X POST "$API_URL/api/v1/runs" \
    -H "Content-Type: application/json" \
    -d "{\"event_id\":\"$EVENT_ID\",\"run_id\":\"$RUN_ID\",\"agent_name\":\"quick_test\",\"job_type\":\"verification\",\"start_time\":\"$(date -Iseconds)\",\"status\":\"running\"}")
status_code="${response:(-3)}"
if [ "$status_code" = "201" ]; then
    test_pass "Create run endpoint working"
else
    test_fail "Create run failed (status=$status_code)"
fi

# Test 3: Get run
echo ""
echo "Test 3: GET /api/v1/runs/{event_id}"
response=$(curl -s -w "%{http_code}" -X GET "$API_URL/api/v1/runs/$EVENT_ID")
status_code="${response:(-3)}"
body="${response:0:-3}"
if [ "$status_code" = "200" ] && echo "$body" | grep -q "\"event_id\":\"$EVENT_ID\""; then
    test_pass "Get run endpoint working"
else
    test_fail "Get run failed (status=$status_code)"
fi

# Test 4: Update run
echo ""
echo "Test 4: PATCH /api/v1/runs/{event_id}"
response=$(curl -s -w "%{http_code}" -X PATCH "$API_URL/api/v1/runs/$EVENT_ID" \
    -H "Content-Type: application/json" \
    -d "{\"status\":\"success\",\"end_time\":\"$(date -Iseconds)\",\"duration_ms\":1000}")
status_code="${response:(-3)}"
if [ "$status_code" = "200" ]; then
    test_pass "Update run endpoint working"
else
    test_fail "Update run failed (status=$status_code)"
fi

# Test 5: List runs
echo ""
echo "Test 5: GET /api/v1/runs (with filters)"
response=$(curl -s -w "%{http_code}" -X GET "$API_URL/api/v1/runs?agent_name=quick_test&limit=10")
status_code="${response:(-3)}"
if [ "$status_code" = "200" ]; then
    test_pass "List runs endpoint working"
else
    test_fail "List runs failed (status=$status_code)"
fi

# Test 6: Associate commit
echo ""
echo "Test 6: POST /api/v1/runs/{event_id}/associate-commit"
response=$(curl -s -w "%{http_code}" -X POST "$API_URL/api/v1/runs/$EVENT_ID/associate-commit" \
    -H "Content-Type: application/json" \
    -d "{\"commit_hash\":\"quick123\",\"commit_source\":\"manual\",\"commit_author\":\"Quick Test <test@test.com>\",\"commit_timestamp\":\"$(date -Iseconds)\"}")
status_code="${response:(-3)}"
if [ "$status_code" = "200" ]; then
    test_pass "Associate commit endpoint working"
else
    test_fail "Associate commit failed (status=$status_code)"
fi

# Verify commit fields stored
verify_response=$(curl -s "$API_URL/api/v1/runs/$EVENT_ID")
if echo "$verify_response" | grep -q '"git_commit_hash":"quick123"'; then
    test_pass "Git commit fields stored correctly"
else
    test_fail "Git commit fields not stored"
fi

# Summary
echo ""
echo "================================================================================"
echo "SUMMARY"
echo "================================================================================"
TOTAL_TESTS=$((PASS_COUNT + FAIL_COUNT))
SUCCESS_RATE=$(( PASS_COUNT * 100 / TOTAL_TESTS ))

echo "Total Tests: $TOTAL_TESTS"
echo "Passed: $PASS_COUNT"
echo "Failed: $FAIL_COUNT"
echo "Success Rate: ${SUCCESS_RATE}%"
echo "================================================================================"

if [ $FAIL_COUNT -eq 0 ]; then
    echo "[SUCCESS] All tests passed!"
    exit 0
else
    echo "[FAILURE] Some tests failed"
    exit 1
fi
