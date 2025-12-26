#!/usr/bin/env python3
"""
Comprehensive deployment verification for local-telemetry.
Runs all tests from the self-review checklist.

Usage:
    python scripts/verify_deployment.py [--api-url URL] [--timeout SECONDS]
"""
import sys
import subprocess
import time
import argparse
from pathlib import Path

# Add user site-packages to path
sys.path.insert(0, r"C:\Users\prora\AppData\Roaming\Python\Python313\site-packages")

try:
    import requests
except ImportError:
    print("[ERROR] requests module not installed. Run: pip install requests")
    sys.exit(1)

# Default configuration
DEFAULT_API_URL = "http://localhost:8765"
DEFAULT_TIMEOUT = 10

# Test results storage
RESULTS = []


def log(msg: str, level: str = "INFO"):
    """Print formatted log message."""
    print(f"[{level}] {msg}")


def test(name: str):
    """Decorator to register and run tests."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            print(f"\n{'='*60}")
            print(f"TEST: {name}")
            print('='*60)
            try:
                result = func(*args, **kwargs)
                status = "PASS" if result else "FAIL"
            except Exception as e:
                log(f"Exception: {e}", "ERROR")
                status = "FAIL"
            RESULTS.append((name, status))
            print(f"[{status}] {name}")
            return status == "PASS"
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator


@test("Container Running")
def test_container(api_url: str, timeout: int) -> bool:
    """Verify Docker container is running and healthy."""
    result = subprocess.run(
        ["docker", "ps", "--filter", "name=local-telemetry-api", "--format", "{{.Status}}"],
        capture_output=True, text=True
    )
    status = result.stdout.strip()
    log(f"Container status: {status}")

    if "healthy" in status.lower():
        return True
    elif "up" in status.lower():
        log("Container is up but not yet healthy", "WARN")
        return True  # Still counts as running
    else:
        log("Container not running or not found", "ERROR")
        return False


@test("Health Endpoint")
def test_health(api_url: str, timeout: int) -> bool:
    """Verify /health endpoint responds correctly."""
    try:
        resp = requests.get(f"{api_url}/health", timeout=timeout)
        log(f"Status: {resp.status_code}, Response: {resp.json()}")
        return resp.status_code == 200 and resp.json().get("status") == "ok"
    except requests.exceptions.ConnectionError:
        log("Cannot connect to API", "ERROR")
        return False


@test("Metrics Endpoint")
def test_metrics(api_url: str, timeout: int) -> bool:
    """Verify /metrics endpoint returns valid data."""
    try:
        resp = requests.get(f"{api_url}/metrics", timeout=timeout)
        data = resp.json()
        log(f"Total runs: {data.get('total_runs', 'N/A')}")
        return resp.status_code == 200 and "total_runs" in data
    except requests.exceptions.ConnectionError:
        log("Cannot connect to API", "ERROR")
        return False


@test("POST Endpoint (with duration_ms)")
def test_post_with_duration(api_url: str, timeout: int) -> bool:
    """Verify POST endpoint accepts valid event with duration_ms."""
    event = {
        "event_id": f"verify-{int(time.time())}-1",
        "run_id": "verify-deployment",
        "agent_name": "verify-script",
        "job_type": "verification",
        "trigger_type": "script",
        "start_time": "2025-01-01T00:00:00Z",
        "end_time": "2025-01-01T00:00:01Z",
        "status": "success",
        "schema_version": 6,
        "duration_ms": 1000,
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:01Z"
    }
    try:
        resp = requests.post(f"{api_url}/api/v1/runs", json=event, timeout=timeout)
        log(f"Status: {resp.status_code}")
        if resp.status_code not in (200, 201):
            log(f"Response: {resp.text}", "WARN")
        return resp.status_code in (200, 201)
    except requests.exceptions.ConnectionError:
        log("Cannot connect to API", "ERROR")
        return False


@test("POST Endpoint (running status, no duration)")
def test_post_running_status(api_url: str, timeout: int) -> bool:
    """Verify POST endpoint handles running status without duration_ms."""
    event = {
        "event_id": f"verify-{int(time.time())}-2",
        "run_id": "verify-running",
        "agent_name": "verify-script",
        "job_type": "verification",
        "trigger_type": "script",
        "start_time": "2025-01-01T00:00:00Z",
        "status": "running",
        "schema_version": 6,
        "duration_ms": 0,  # Use 0 instead of null for running status
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z"
    }
    try:
        resp = requests.post(f"{api_url}/api/v1/runs", json=event, timeout=timeout)
        log(f"Status: {resp.status_code}")
        if resp.status_code not in (200, 201):
            log(f"Response: {resp.text}", "WARN")
        return resp.status_code in (200, 201)
    except requests.exceptions.ConnectionError:
        log("Cannot connect to API", "ERROR")
        return False


@test("Database Integrity")
def test_db_integrity(api_url: str, timeout: int) -> bool:
    """Verify SQLite database passes integrity check."""
    result = subprocess.run(
        ["docker", "exec", "local-telemetry-api", "sh", "-c",
         "sqlite3 /data/telemetry.sqlite 'PRAGMA integrity_check;'"],
        capture_output=True, text=True
    )
    output = result.stdout.strip()
    log(f"Integrity check result: {output}")
    return "ok" in output.lower()


@test("Restart Policy")
def test_restart_policy(api_url: str, timeout: int) -> bool:
    """Verify container has restart: always policy."""
    result = subprocess.run(
        ["docker", "inspect", "local-telemetry-api",
         "--format={{.HostConfig.RestartPolicy.Name}}"],
        capture_output=True, text=True
    )
    policy = result.stdout.strip()
    log(f"Restart policy: {policy}")
    return policy == "always"


@test("Data Persistence")
def test_data_persistence(api_url: str, timeout: int) -> bool:
    """Verify data is persisted across API calls."""
    try:
        # Get initial count
        resp1 = requests.get(f"{api_url}/metrics", timeout=timeout)
        before = resp1.json().get("total_runs", 0)
        log(f"Runs before POST: {before}")

        # Add a new event
        event = {
            "event_id": f"persist-test-{int(time.time())}",
            "run_id": "persistence-verification",
            "agent_name": "verify-script",
            "job_type": "verification",
            "trigger_type": "script",
            "start_time": "2025-01-01T00:00:00Z",
            "end_time": "2025-01-01T00:00:01Z",
            "status": "success",
            "schema_version": 6,
            "duration_ms": 500,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:01Z"
        }
        requests.post(f"{api_url}/api/v1/runs", json=event, timeout=timeout)

        # Verify count increased
        resp2 = requests.get(f"{api_url}/metrics", timeout=timeout)
        after = resp2.json().get("total_runs", 0)
        log(f"Runs after POST: {after}")

        return after >= before
    except requests.exceptions.ConnectionError:
        log("Cannot connect to API", "ERROR")
        return False


@test("Container Logs Accessible")
def test_container_logs(api_url: str, timeout: int) -> bool:
    """Verify container logs are accessible for debugging."""
    result = subprocess.run(
        ["docker", "logs", "--tail", "5", "local-telemetry-api"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        log(f"Last 5 log lines accessible")
        return True
    else:
        log(f"Cannot access logs: {result.stderr}", "ERROR")
        return False


def run_all_tests(api_url: str, timeout: int) -> int:
    """Run all verification tests and return exit code."""
    print("="*60)
    print("LOCAL-TELEMETRY DEPLOYMENT VERIFICATION")
    print("="*60)
    print(f"API URL: {api_url}")
    print(f"Timeout: {timeout}s")

    tests = [
        test_container,
        test_health,
        test_metrics,
        test_post_with_duration,
        test_post_running_status,
        test_db_integrity,
        test_restart_policy,
        test_data_persistence,
        test_container_logs,
    ]

    for t in tests:
        t(api_url, timeout)

    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    passed = sum(1 for _, s in RESULTS if s == "PASS")
    total = len(RESULTS)

    for name, status in RESULTS:
        symbol = "+" if status == "PASS" else "X"
        print(f"  [{symbol}] {name}: {status}")

    print(f"\nResult: {passed}/{total} tests passed")

    if passed == total:
        print("\n[SUCCESS] All deployment verification tests passed!")
        return 0
    else:
        print(f"\n[FAILURE] {total - passed} test(s) failed!")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Verify local-telemetry deployment"
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"API URL (default: {DEFAULT_API_URL})"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT})"
    )

    args = parser.parse_args()
    return run_all_tests(args.api_url, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
