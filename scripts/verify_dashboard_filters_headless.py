#!/usr/bin/env python3
"""
Automated Dashboard Filter Verification Harness.

Starts an isolated telemetry API instance, seeds deterministic data, and verifies
filter correctness and event fetching without manual UI interaction.
"""

import os
import sys
import time
import uuid
import json
import socket
import shutil
import signal
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


DEFAULT_HOST = "127.0.0.1"
DEFAULT_TIMEOUT = 5


class HarnessError(Exception):
    pass


def log(message: str, level: str = "INFO") -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((DEFAULT_HOST, 0))
        return sock.getsockname()[1]


def build_temp_paths() -> Tuple[Path, Path]:
    temp_root = Path(os.getenv("TEMP", "/tmp"))
    db_path = temp_root / f"telemetry_test_{uuid.uuid4().hex[:8]}.sqlite"
    lock_path = db_path.with_suffix(".lock")
    return db_path, lock_path


def start_api(db_path: Path, lock_path: Path, port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env["TELEMETRY_DB_PATH"] = str(db_path)
    env["TELEMETRY_LOCK_FILE"] = str(lock_path)
    env["TELEMETRY_API_HOST"] = DEFAULT_HOST
    env["TELEMETRY_API_PORT"] = str(port)
    env["TELEMETRY_DB_JOURNAL_MODE"] = "DELETE"
    env["TELEMETRY_DB_SYNCHRONOUS"] = "FULL"

    log(f"Starting API on {DEFAULT_HOST}:{port} with db={db_path}")
    return subprocess.Popen(
        [sys.executable, "telemetry_service.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def stop_api(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    log("Stopping API process")
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        log("API did not stop in time, killing process", "WARN")
        proc.kill()


def wait_for_api(base_url: str, proc: subprocess.Popen, max_attempts: int = 30) -> None:
    for attempt in range(max_attempts):
        if proc.poll() is not None:
            output = proc.stdout.read() if proc.stdout else ""
            raise HarnessError(f"API process exited early. Output:\n{output}")
        try:
            response = requests.get(f"{base_url}/health", timeout=DEFAULT_TIMEOUT)
            if response.status_code == 200:
                log(f"API is ready (attempt {attempt + 1}/{max_attempts})")
                return
        except requests.RequestException:
            time.sleep(1)
    raise HarnessError("API did not become ready in time")


def create_test_run(base_url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    response = requests.post(f"{base_url}/api/v1/runs", json=payload, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()


def query_runs(base_url: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    response = requests.get(f"{base_url}/api/v1/runs", params=params or {}, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()


def fetch_run(base_url: str, event_id: str) -> Dict[str, Any]:
    response = requests.get(f"{base_url}/api/v1/runs/{event_id}", timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()


def make_payload(
    event_id: str,
    run_id: str,
    agent_name: str,
    status: str,
    job_type: str,
    parent_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    payload = {
        "event_id": event_id,
        "run_id": run_id,
        "agent_name": agent_name,
        "job_type": job_type,
        "status": status,
        "start_time": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        "end_time": datetime.now(timezone.utc).isoformat(),
        "duration_ms": 60000,
        "items_discovered": 100,
        "items_succeeded": 95,
        "items_failed": 5,
        "items_skipped": 0,
    }
    if parent_run_id:
        payload["parent_run_id"] = parent_run_id
    return payload


def seed_dataset(base_url: str) -> Dict[str, Any]:
    seed = {}

    parent_event = str(uuid.uuid4())
    parent_run_id = f"run-parent-{parent_event[:8]}"
    create_test_run(
        base_url,
        make_payload(parent_event, parent_run_id, "agent-alpha", "running", "analysis"),
    )

    alias_cases = [
        ("failed", "failure"),
        ("failure", "failure"),
        ("completed", "success"),
        ("success", "success"),
        ("succeeded", "success"),
    ]

    alias_event_ids = []
    for status, _canonical in alias_cases:
        event_id = str(uuid.uuid4())
        alias_event_ids.append(event_id)
        create_test_run(
            base_url,
            make_payload(event_id, f"run-{event_id[:8]}", "agent-alpha", status, "batch"),
        )

    child_event = str(uuid.uuid4())
    child_run_id = f"run-child-{child_event[:8]}"
    create_test_run(
        base_url,
        make_payload(child_event, child_run_id, "agent-beta", "success", "sync", parent_run_id=parent_run_id),
    )

    test_job_event = str(uuid.uuid4())
    create_test_run(
        base_url,
        make_payload(test_job_event, f"run-test-{test_job_event[:8]}", "agent-beta", "success", "test"),
    )

    seed["parent_event"] = parent_event
    seed["parent_run_id"] = parent_run_id
    seed["child_event"] = child_event
    seed["child_run_id"] = child_run_id
    seed["alias_event_ids"] = alias_event_ids
    seed["alias_cases"] = alias_cases
    seed["test_job_event"] = test_job_event

    return seed


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise HarnessError(message)


def test_alias_normalization(base_url: str, seed: Dict[str, Any]) -> None:
    for event_id, (raw_status, canonical) in zip(seed["alias_event_ids"], seed["alias_cases"]):
        run = fetch_run(base_url, event_id)
        actual = run.get("status")
        assert_true(
            actual == canonical,
            f"Alias normalization failed for status '{raw_status}': got '{actual}', expected '{canonical}'",
        )


def test_multi_status_filter(base_url: str) -> None:
    params = [("status", "success"), ("status", "failure")]
    response = requests.get(f"{base_url}/api/v1/runs", params=params, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    results = response.json()
    statuses = {r.get("status") for r in results}
    assert_true(statuses.issubset({"success", "failure"}), f"Unexpected statuses in multi-status filter: {statuses}")


def test_job_type_filter(base_url: str) -> None:
    results = query_runs(base_url, {"job_type": "sync"})
    assert_true(results, "Expected job_type=sync results")
    job_types = {r.get("job_type") for r in results}
    assert_true(job_types == {"sync"}, f"Job type filter returned {job_types}")


def test_parent_run_filter(base_url: str, seed: Dict[str, Any]) -> None:
    results = query_runs(base_url, {"parent_run_id": seed["parent_run_id"]})
    assert_true(results, "Expected parent_run_id filter results")
    parent_ids = {r.get("parent_run_id") for r in results}
    assert_true(parent_ids == {seed["parent_run_id"]}, f"parent_run_id filter returned {parent_ids}")


def test_run_id_contains_filter(base_url: str, seed: Dict[str, Any]) -> None:
    fragment = seed["child_run_id"].split("-")[-1]
    results = query_runs(base_url, {"run_id_contains": fragment})
    assert_true(results, "Expected run_id_contains results")
    run_ids = {r.get("run_id") for r in results}
    assert_true(seed["child_run_id"] in run_ids, f"run_id_contains did not include {seed['child_run_id']}")


def test_exclude_job_type(base_url: str) -> None:
    results = query_runs(base_url, {"exclude_job_type": "test"})
    job_types = {r.get("job_type") for r in results}
    assert_true("test" not in job_types, f"exclude_job_type still returned {job_types}")


def test_event_id_fetch(base_url: str, seed: Dict[str, Any]) -> None:
    run = fetch_run(base_url, seed["child_event"])
    assert_true(run.get("event_id") == seed["child_event"], "Event_id fetch returned wrong run")


def run_tests(base_url: str, seed: Dict[str, Any]) -> None:
    test_alias_normalization(base_url, seed)
    test_multi_status_filter(base_url)
    test_job_type_filter(base_url)
    test_parent_run_filter(base_url, seed)
    test_run_id_contains_filter(base_url, seed)
    test_exclude_job_type(base_url)
    test_event_id_fetch(base_url, seed)


def main() -> int:
    if not HAS_REQUESTS:
        log("requests module required. Install with: pip install requests", "ERROR")
        return 1

    db_path, lock_path = build_temp_paths()
    port = find_free_port()
    base_url = f"http://{DEFAULT_HOST}:{port}"

    proc = start_api(db_path, lock_path, port)
    try:
        wait_for_api(base_url, proc)
        seed = seed_dataset(base_url)
        run_tests(base_url, seed)
        log("All headless dashboard filter tests passed", "PASS")
        return 0
    except Exception as exc:
        log(f"Headless dashboard filter tests failed: {exc}", "FAIL")
        return 1
    finally:
        stop_api(proc)
        if db_path.exists():
            try:
                shutil.copy2(db_path, db_path.with_suffix(".seeded.sqlite"))
            except Exception:
                pass
            try:
                db_path.unlink()
            except Exception:
                pass
        if lock_path.exists():
            try:
                lock_path.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
