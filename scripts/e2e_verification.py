"""
Comprehensive E2E verification of the telemetry API.

Tests all endpoints in order:
1. GET /health - verify status=ok
2. POST /api/v1/runs - create a test run
3. GET /api/v1/runs/{event_id} - retrieve the run
4. PATCH /api/v1/runs/{event_id} - update the run
5. GET /api/v1/runs - list runs with filters
6. POST /api/v1/runs/{event_id}/associate-commit - associate a git commit
7. GET /api/v1/runs/count - get run count
8. GET /api/v1/stats - get statistics

Reports status code, response time, success/failure, and errors for each endpoint.
"""

import requests
import time
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import uuid


class E2EVerification:
    """E2E verification test runner for telemetry API."""

    def __init__(self, base_url: str = "http://localhost:8765"):
        """Initialize E2E verification."""
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.results = []
        self.test_event_id = None
        self.test_run_id = None

    def log_result(
        self,
        test_name: str,
        endpoint: str,
        status_code: Optional[int],
        response_time: float,
        success: bool,
        error: Optional[str] = None,
        response_data: Optional[Dict[str, Any]] = None
    ):
        """Log test result."""
        result = {
            "test": test_name,
            "endpoint": endpoint,
            "status_code": status_code,
            "response_time_ms": round(response_time * 1000, 2),
            "success": success,
            "error": error,
            "response_data": response_data
        }
        self.results.append(result)
        return result

    def print_result(self, result: Dict[str, Any]):
        """Print formatted test result."""
        status = "✓ PASS" if result["success"] else "✗ FAIL"
        print(f"\n{status} - {result['test']}")
        print(f"  Endpoint: {result['endpoint']}")
        print(f"  Status Code: {result['status_code']}")
        print(f"  Response Time: {result['response_time_ms']}ms")
        if result["error"]:
            print(f"  Error: {result['error']}")
        if result["response_data"]:
            print(f"  Response: {json.dumps(result['response_data'], indent=2)[:200]}")

    def test_health(self) -> bool:
        """Test 1: GET /health - verify status=ok."""
        endpoint = f"{self.base_url}/health"
        test_name = "1. GET /health"

        try:
            start_time = time.time()
            response = self.session.get(endpoint, timeout=10)
            elapsed = time.time() - start_time

            data = response.json()
            success = response.status_code == 200 and data.get("status") == "ok"
            error = None if success else f"Expected status=ok, got {data.get('status')}"

            result = self.log_result(
                test_name, endpoint, response.status_code, elapsed,
                success, error, data
            )
            self.print_result(result)
            return success

        except Exception as e:
            result = self.log_result(
                test_name, endpoint, None, 0, False, str(e)
            )
            self.print_result(result)
            return False

    def test_create_run(self) -> bool:
        """Test 2: POST /api/v1/runs - create a test run."""
        endpoint = f"{self.base_url}/api/v1/runs"
        test_name = "2. POST /api/v1/runs"

        # Generate unique test data
        unique_id = str(uuid.uuid4())[:8]
        self.test_event_id = f"e2e_test_{unique_id}"
        self.test_run_id = f"run_{unique_id}"

        payload = {
            "event_id": self.test_event_id,
            "run_id": self.test_run_id,
            "agent_name": "e2e_test_agent",
            "job_type": "e2e_verification",
            "status": "running",
            "start_time": datetime.now(timezone.utc).isoformat()
        }

        try:
            start_time = time.time()
            response = self.session.post(endpoint, json=payload, timeout=10)
            elapsed = time.time() - start_time

            data = response.json()
            success = response.status_code in (200, 201) and data.get("status") in ("created", "duplicate")
            error = None if success else f"Unexpected response: {data}"

            result = self.log_result(
                test_name, endpoint, response.status_code, elapsed,
                success, error, data
            )
            self.print_result(result)
            return success

        except Exception as e:
            result = self.log_result(
                test_name, endpoint, None, 0, False, str(e)
            )
            self.print_result(result)
            return False

    def test_get_run(self) -> bool:
        """Test 3: GET /api/v1/runs/{event_id} - retrieve the run."""
        if not self.test_event_id:
            print("\n✗ SKIP - Test 3: No event_id from previous test")
            return False

        endpoint = f"{self.base_url}/api/v1/runs/{self.test_event_id}"
        test_name = "3. GET /api/v1/runs/{event_id}"

        try:
            start_time = time.time()
            response = self.session.get(endpoint, timeout=10)
            elapsed = time.time() - start_time

            data = response.json()
            success = (
                response.status_code == 200
                and data.get("event_id") == self.test_event_id
                and data.get("run_id") == self.test_run_id
            )
            error = None if success else f"Data mismatch or error: {data}"

            result = self.log_result(
                test_name, endpoint, response.status_code, elapsed,
                success, error, data
            )
            self.print_result(result)
            return success

        except Exception as e:
            result = self.log_result(
                test_name, endpoint, None, 0, False, str(e)
            )
            self.print_result(result)
            return False

    def test_update_run(self) -> bool:
        """Test 4: PATCH /api/v1/runs/{event_id} - update the run."""
        if not self.test_event_id:
            print("\n✗ SKIP - Test 4: No event_id from previous test")
            return False

        endpoint = f"{self.base_url}/api/v1/runs/{self.test_event_id}"
        test_name = "4. PATCH /api/v1/runs/{event_id}"

        payload = {
            "status": "success",
            "end_time": datetime.now(timezone.utc).isoformat(),
            "duration_ms": 12345,
            "output_summary": "e2e_patch_test"
        }

        try:
            start_time = time.time()
            response = self.session.patch(endpoint, json=payload, timeout=10)
            elapsed = time.time() - start_time

            data = response.json()
            success = (
                response.status_code == 200
                and data.get("event_id") == self.test_event_id
            )
            error = None if success else f"Update failed: {data}"

            result = self.log_result(
                test_name, endpoint, response.status_code, elapsed,
                success, error, data
            )
            self.print_result(result)
            return success

        except Exception as e:
            result = self.log_result(
                test_name, endpoint, None, 0, False, str(e)
            )
            self.print_result(result)
            return False

    def test_list_runs(self) -> bool:
        """Test 5: GET /api/v1/runs - list runs with filters."""
        endpoint = f"{self.base_url}/api/v1/runs"
        test_name = "5. GET /api/v1/runs (with filters)"

        # Test with multiple filter combinations
        params = {
            "agent_name": "e2e_test_agent",
            "status": "success",
            "limit": 10
        }

        try:
            start_time = time.time()
            response = self.session.get(endpoint, params=params, timeout=10)
            elapsed = time.time() - start_time

            data = response.json()
            success = (
                response.status_code == 200
                and isinstance(data.get("runs"), list)
                and "total" in data
            )
            error = None if success else f"Invalid response format: {data}"

            # Verify our test run is in the results
            if success and self.test_event_id:
                found = any(run.get("event_id") == self.test_event_id for run in data["runs"])
                if not found:
                    error = f"Test run {self.test_event_id} not found in results"
                    success = False

            result = self.log_result(
                test_name, endpoint, response.status_code, elapsed,
                success, error, data
            )
            self.print_result(result)
            return success

        except Exception as e:
            result = self.log_result(
                test_name, endpoint, None, 0, False, str(e)
            )
            self.print_result(result)
            return False

    def test_associate_commit(self) -> bool:
        """Test 6: POST /api/v1/runs/{event_id}/associate-commit - associate a git commit."""
        if not self.test_event_id:
            print("\n✗ SKIP - Test 6: No event_id from previous test")
            return False

        endpoint = f"{self.base_url}/api/v1/runs/{self.test_event_id}/associate-commit"
        test_name = "6. POST /api/v1/runs/{event_id}/associate-commit"

        payload = {
            "commit_hash": "abc123def456",
            "commit_source": "manual",
            "commit_author": "E2E Test <e2e@test.com>",
            "commit_timestamp": datetime.now(timezone.utc).isoformat()
        }

        try:
            start_time = time.time()
            response = self.session.post(endpoint, json=payload, timeout=10)
            elapsed = time.time() - start_time

            data = response.json()
            success = (
                response.status_code == 200
                and data.get("event_id") == self.test_event_id
                and data.get("commit_hash") == payload["commit_hash"]
            )
            error = None if success else f"Commit association failed: {data}"

            result = self.log_result(
                test_name, endpoint, response.status_code, elapsed,
                success, error, data
            )
            self.print_result(result)

            # Verify the commit fields were stored by re-fetching the run
            if success:
                verify_endpoint = f"{self.base_url}/api/v1/runs/{self.test_event_id}"
                verify_response = self.session.get(verify_endpoint, timeout=10)
                if verify_response.status_code == 200:
                    verify_data = verify_response.json()
                    if verify_data.get("git_commit_hash") != payload["commit_hash"]:
                        error = "Commit hash not stored correctly"
                        success = False
                    if verify_data.get("git_commit_source") != payload["commit_source"]:
                        error = "Commit source not stored correctly"
                        success = False
                    if verify_data.get("git_commit_author") != payload["commit_author"]:
                        error = "Commit author not stored correctly"
                        success = False
                    print(f"  Verification: git_commit_hash={verify_data.get('git_commit_hash')}")
                    print(f"  Verification: git_commit_source={verify_data.get('git_commit_source')}")
                    print(f"  Verification: git_commit_author={verify_data.get('git_commit_author')}")

            return success

        except Exception as e:
            result = self.log_result(
                test_name, endpoint, None, 0, False, str(e)
            )
            self.print_result(result)
            return False

    def test_get_count(self) -> bool:
        """Test 7: GET /api/v1/runs/count - get run count."""
        endpoint = f"{self.base_url}/api/v1/runs/count"
        test_name = "7. GET /api/v1/runs/count"

        # Test with filters
        params = {
            "agent_name": "e2e_test_agent",
            "status": "success"
        }

        try:
            start_time = time.time()
            response = self.session.get(endpoint, params=params, timeout=10)
            elapsed = time.time() - start_time

            data = response.json()
            success = (
                response.status_code == 200
                and "count" in data
                and isinstance(data["count"], int)
                and data["count"] >= 0
            )
            error = None if success else f"Invalid count response: {data}"

            result = self.log_result(
                test_name, endpoint, response.status_code, elapsed,
                success, error, data
            )
            self.print_result(result)
            return success

        except Exception as e:
            result = self.log_result(
                test_name, endpoint, None, 0, False, str(e)
            )
            self.print_result(result)
            return False

    def test_get_stats(self) -> bool:
        """Test 8: GET /api/v1/stats - get statistics."""
        endpoint = f"{self.base_url}/api/v1/stats"
        test_name = "8. GET /api/v1/stats"

        try:
            start_time = time.time()
            response = self.session.get(endpoint, timeout=10)
            elapsed = time.time() - start_time

            data = response.json()
            success = (
                response.status_code == 200
                and "total_runs" in data
                and "agents" in data
                and isinstance(data["total_runs"], int)
            )
            error = None if success else f"Invalid stats response: {data}"

            result = self.log_result(
                test_name, endpoint, response.status_code, elapsed,
                success, error, data
            )
            self.print_result(result)
            return success

        except Exception as e:
            result = self.log_result(
                test_name, endpoint, None, 0, False, str(e)
            )
            self.print_result(result)
            return False

    def run_all_tests(self):
        """Run all E2E verification tests."""
        print("=" * 80)
        print("TELEMETRY API E2E VERIFICATION")
        print(f"Base URL: {self.base_url}")
        print(f"Started: {datetime.now().isoformat()}")
        print("=" * 80)

        # Run tests in order
        tests = [
            self.test_health,
            self.test_create_run,
            self.test_get_run,
            self.test_update_run,
            self.test_list_runs,
            self.test_associate_commit,
            self.test_get_count,
            self.test_get_stats,
        ]

        for test_fn in tests:
            test_fn()

        # Print summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)

        total = len(self.results)
        passed = sum(1 for r in self.results if r["success"])
        failed = total - passed

        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {(passed/total*100):.1f}%")

        # Print failed tests
        if failed > 0:
            print("\nFailed Tests:")
            for r in self.results:
                if not r["success"]:
                    print(f"  - {r['test']}: {r['error']}")

        # Print performance stats
        print("\nPerformance:")
        total_time = sum(r["response_time_ms"] for r in self.results)
        avg_time = total_time / total if total > 0 else 0
        print(f"  Total Time: {total_time:.2f}ms")
        print(f"  Average Time: {avg_time:.2f}ms")
        print(f"  Min Time: {min(r['response_time_ms'] for r in self.results):.2f}ms")
        print(f"  Max Time: {max(r['response_time_ms'] for r in self.results):.2f}ms")

        print("\n" + "=" * 80)
        print(f"Completed: {datetime.now().isoformat()}")
        print("=" * 80)

        return passed == total


def main():
    """Run E2E verification."""
    verifier = E2EVerification(base_url="http://localhost:8765")
    success = verifier.run_all_tests()

    # Save results to file
    results_file = "e2e_verification_results.json"
    with open(results_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "base_url": verifier.base_url,
            "results": verifier.results,
            "summary": {
                "total": len(verifier.results),
                "passed": sum(1 for r in verifier.results if r["success"]),
                "failed": sum(1 for r in verifier.results if not r["success"]),
            }
        }, f, indent=2)

    print(f"\nResults saved to: {results_file}")

    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
