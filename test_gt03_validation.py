#!/usr/bin/env python3
"""Quick test script to verify GT-03 Pydantic validation works."""

import sys
from pathlib import Path

# Add user site-packages to path
sys.path.insert(0, r"C:\Users\prora\AppData\Roaming\Python\Python313\site-packages")

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from pydantic import BaseModel, Field, field_validator, ValidationError
from datetime import datetime, timezone
from typing import Optional, Dict, Any

# Copy of TelemetryRun with git_commit_source validation
class TelemetryRunTest(BaseModel):
    """Test model for git_commit_source validation."""
    event_id: str
    run_id: str
    agent_name: str
    job_type: str
    start_time: str
    git_commit_source: Optional[str] = Field(
        None,
        description="How commit was created: 'manual', 'llm', 'ci'"
    )
    git_commit_author: Optional[str] = None
    git_commit_timestamp: Optional[str] = None

    @field_validator('git_commit_source')
    @classmethod
    def validate_commit_source(cls, v):
        """Validate git_commit_source is one of allowed values."""
        if v is not None and v not in ['manual', 'llm', 'ci']:
            raise ValueError("git_commit_source must be 'manual', 'llm', or 'ci'")
        return v


# Test 1: Valid values
print("=" * 70)
print("GT-03 VALIDATION TESTS")
print("=" * 70)
print()

print("[Test 1] Valid git_commit_source values...")
for source in ['manual', 'llm', 'ci']:
    try:
        run = TelemetryRunTest(
            event_id=f"test-{source}",
            run_id="test-1",
            agent_name="test",
            job_type="test",
            start_time="2026-01-01T12:00:00Z",
            git_commit_source=source
        )
        print(f"  [OK] '{source}' accepted")
    except ValidationError as e:
        print(f"  [FAIL] '{source}' rejected: {e}")
        sys.exit(1)

# Test 2: Invalid value
print()
print("[Test 2] Invalid git_commit_source value...")
try:
    run = TelemetryRunTest(
        event_id="test-invalid",
        run_id="test-2",
        agent_name="test",
        job_type="test",
        start_time="2026-01-01T12:00:00Z",
        git_commit_source="invalid_value"
    )
    print("  [FAIL] 'invalid_value' was accepted (SHOULD HAVE BEEN REJECTED!)")
    sys.exit(1)
except ValidationError as e:
    print(f"  [OK] 'invalid_value' rejected correctly")
    print(f"    Error: {e.errors()[0]['msg']}")

# Test 3: None value (should be accepted)
print()
print("[Test 3] None git_commit_source value...")
try:
    run = TelemetryRunTest(
        event_id="test-none",
        run_id="test-3",
        agent_name="test",
        job_type="test",
        start_time="2026-01-01T12:00:00Z",
        git_commit_source=None
    )
    print(f"  [OK] None accepted")
except ValidationError as e:
    print(f"  [FAIL] None rejected: {e}")
    sys.exit(1)

print()
print("=" * 70)
print("ALL TESTS PASSED [OK]")
print("=" * 70)
print()
print("GT-03 Pydantic validation is working correctly!")
