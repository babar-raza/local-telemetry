#!/usr/bin/env python3
"""
Spec Consistency Verification

Verifies that specs/features/ match the actual telemetry_service.py implementation
by checking the FastAPI OpenAPI schema.

Usage:
    python scripts/verify_spec_consistency.py

Requirements:
    - telemetry_service.py running on localhost:8765 OR
    - Can import telemetry_service module directly

Exit codes:
    0 - All checks passed
    1 - Spec drift detected or errors occurred
"""

import sys
import json
from pathlib import Path


def get_openapi_schema():
    """
    Get OpenAPI schema from running service or by importing the module.

    Returns:
        dict: OpenAPI schema
    """
    # Try to get from running service first
    try:
        import requests
        response = requests.get("http://localhost:8765/openapi.json", timeout=5)
        if response.status_code == 200:
            print("[OK] Retrieved OpenAPI schema from running service")
            return response.json()
    except Exception as e:
        print(f"[INFO] Cannot reach running service: {e}")
        print("[INFO] Will import telemetry_service module directly")

    # Fallback: import the module
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        import telemetry_service
        schema = telemetry_service.app.openapi()
        print("[OK] Generated OpenAPI schema from imported module")
        return schema
    except Exception as e:
        print(f"[ERROR] Cannot import telemetry_service: {e}")
        return None


def verify_query_runs_endpoint(schema):
    """
    Verify GET /api/v1/runs endpoint matches spec.

    Spec location: specs/features/http_query_runs.md

    Expected params (from Phase 2 spec update):
    - agent_name (string, optional)
    - status (string, optional)
    - job_type (string, optional)
    - limit (integer, default 100, constraints 1-1000)
    - offset (integer, default 0, minimum 0)

    NOT expected (removed in Phase 2):
    - created_before, created_after, start_time_from, start_time_to
    """
    print("\n" + "=" * 70)
    print("Checking: GET /api/v1/runs")
    print("=" * 70)

    endpoint = schema.get("paths", {}).get("/api/v1/runs", {}).get("get", {})

    if not endpoint:
        print("[FAIL] Endpoint /api/v1/runs GET not found in OpenAPI schema")
        return False

    params = {p["name"]: p for p in endpoint.get("parameters", [])}

    issues = []

    # Check expected parameters
    expected = {
        "agent_name": {"type": "string", "required": False},
        "status": {"type": "string", "required": False},
        "job_type": {"type": "string", "required": False},
        "limit": {"type": "integer", "required": False},
        "offset": {"type": "integer", "required": False},
    }

    for param_name, expected_config in expected.items():
        if param_name not in params:
            issues.append(f"Missing parameter: {param_name}")
            continue

        param = params[param_name]
        schema_type = param.get("schema", {}).get("type")

        if schema_type != expected_config["type"]:
            issues.append(f"{param_name}: expected type {expected_config['type']}, got {schema_type}")

        is_required = param.get("required", False)
        if is_required != expected_config["required"]:
            issues.append(f"{param_name}: expected required={expected_config['required']}, got {is_required}")

    # Check limit constraints
    if "limit" in params:
        limit_schema = params["limit"].get("schema", {})
        if limit_schema.get("maximum") != 1000:
            issues.append(f"limit: expected maximum=1000, got {limit_schema.get('maximum')}")
        if limit_schema.get("minimum") != 1:
            issues.append(f"limit: expected minimum=1, got {limit_schema.get('minimum')}")

    # Check offset constraints
    if "offset" in params:
        offset_schema = params["offset"].get("schema", {})
        if offset_schema.get("minimum") != 0:
            issues.append(f"offset: expected minimum=0, got {offset_schema.get('minimum')}")

    # Check for parameters that should NOT exist (removed in Phase 2)
    removed_params = ["created_before", "created_after", "start_time_from", "start_time_to"]
    for param_name in removed_params:
        if param_name in params:
            issues.append(f"Unexpected parameter (should be removed): {param_name}")

    # Report results
    if issues:
        print("[FAIL] Spec drift detected:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    else:
        print("[OK] All parameters match spec")
        print(f"  - agent_name: optional string")
        print(f"  - status: optional string (normalized)")
        print(f"  - job_type: optional string")
        print(f"  - limit: optional integer (1-1000, default 100)")
        print(f"  - offset: optional integer (>=0, default 0)")
        return True


def verify_create_run_endpoint(schema):
    """
    Verify POST /api/v1/runs endpoint exists.

    Spec location: specs/features/http_create_run.md
    """
    print("\n" + "=" * 70)
    print("Checking: POST /api/v1/runs")
    print("=" * 70)

    endpoint = schema.get("paths", {}).get("/api/v1/runs", {}).get("post", {})

    if not endpoint:
        print("[FAIL] Endpoint /api/v1/runs POST not found in OpenAPI schema")
        return False

    print("[OK] Endpoint exists")

    # Check request body schema exists
    request_body = endpoint.get("requestBody", {})
    if not request_body:
        print("[WARN] No requestBody schema found")
        return True

    # Check that it references RunCreate model
    content = request_body.get("content", {}).get("application/json", {})
    schema_ref = content.get("schema", {}).get("$ref", "")

    if "RunCreate" in schema_ref:
        print("[OK] Uses RunCreate model")
    else:
        print(f"[WARN] Expected RunCreate model, got: {schema_ref}")

    return True


def verify_status_aliases(schema):
    """
    Verify that status normalization is documented in spec.

    Spec location: specs/_index.md (Invariant 7)
    """
    print("\n" + "=" * 70)
    print("Checking: Status Alias Documentation")
    print("=" * 70)

    spec_index = Path(__file__).parent.parent / "specs" / "_index.md"

    if not spec_index.exists():
        print("[FAIL] specs/_index.md not found")
        return False

    content = spec_index.read_text()

    # Check for status aliases
    required_terms = [
        "Status Aliases",
        "failed",
        "failure",
        "completed",
        "success",
        "normalize_status",
    ]

    missing = []
    for term in required_terms:
        if term not in content:
            missing.append(term)

    if missing:
        print(f"[FAIL] Missing terms in specs/_index.md: {missing}")
        return False

    print("[OK] Status aliases documented in specs/_index.md")
    print("  - failed → failure")
    print("  - completed → success")
    print("  - succeeded → success")

    return True


def verify_http_query_runs_spec(schema):
    """
    Verify that specs/features/http_query_runs.md matches implementation.
    """
    print("\n" + "=" * 70)
    print("Checking: specs/features/http_query_runs.md")
    print("=" * 70)

    spec_file = Path(__file__).parent.parent / "specs" / "features" / "http_query_runs.md"

    if not spec_file.exists():
        print("[FAIL] specs/features/http_query_runs.md not found")
        return False

    content = spec_file.read_text()

    # Check that date/time filters are marked as NOT IMPLEMENTED
    if "created_before" in content and "NOT YET IMPLEMENTED" not in content:
        print("[FAIL] Spec mentions created_before but doesn't mark it as NOT IMPLEMENTED")
        return False

    # Check for status alias documentation
    if "Status Alias" not in content and "normalize" not in content:
        print("[WARN] Spec should document status alias normalization")

    # Check for computed fields documentation
    if "commit_url" not in content or "repo_url" not in content:
        print("[WARN] Spec should document computed fields (commit_url, repo_url)")

    print("[OK] Spec file exists and appears up to date")

    return True


def main():
    """Run all consistency checks."""
    print("=" * 70)
    print("SPEC CONSISTENCY VERIFICATION")
    print("=" * 70)
    print("")
    print("Verifying that specs/ match telemetry_service.py implementation")
    print("")

    # Get OpenAPI schema
    schema = get_openapi_schema()
    if not schema:
        print("\n[FAIL] Cannot retrieve OpenAPI schema")
        return 1

    # Run checks
    checks = [
        ("Query Runs Endpoint", lambda: verify_query_runs_endpoint(schema)),
        ("Create Run Endpoint", lambda: verify_create_run_endpoint(schema)),
        ("Status Aliases", lambda: verify_status_aliases(schema)),
        ("Query Runs Spec File", lambda: verify_http_query_runs_spec(schema)),
    ]

    results = []
    for name, check_fn in checks:
        try:
            passed = check_fn()
            results.append((name, passed))
        except Exception as e:
            print(f"\n[ERROR] {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {name}")

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    print("")
    print(f"Passed: {passed_count}/{total_count}")

    if passed_count == total_count:
        print("\n✓ All spec consistency checks passed")
        return 0
    else:
        print(f"\n✗ {total_count - passed_count} check(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
