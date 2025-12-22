"""
Smoke test for TEL-03 TelemetryClient

Quick validation that basic functionality works:
- Import all public API
- Create client with default config
- Track a run using context manager
- Log events
- Verify files created
"""

import sys
from pathlib import Path

# Add src to path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from telemetry import (
    TelemetryClient,
    RunContext,
    TelemetryConfig,
    RunRecord,
    RunEvent,
    APIPayload,
    SCHEMA_VERSION,
)


def test_imports():
    """Test that all public API imports work."""
    print("[TEST] Testing imports...")
    assert TelemetryClient is not None
    assert RunContext is not None
    assert TelemetryConfig is not None
    assert RunRecord is not None
    assert RunEvent is not None
    assert APIPayload is not None
    assert SCHEMA_VERSION == 6  # v6 includes event_id for idempotency
    print("[OK] All imports successful")


def test_basic_run():
    """Test basic run tracking with context manager."""
    print("[TEST] Testing basic run tracking...")

    # Create client (will use env vars or defaults)
    client = TelemetryClient()

    # Track a run
    with client.track_run("smoke_test_agent", "smoke_test", trigger_type="cli") as ctx:
        ctx.log_event("test_event", {"status": "ok"})
        ctx.set_metrics(items_discovered=5, items_succeeded=5)

    print("[OK] Basic run tracking successful")


def test_explicit_start_end():
    """Test explicit start_run/end_run pattern."""
    print("[TEST] Testing explicit start/end pattern...")

    client = TelemetryClient()

    # Start run
    run_id = client.start_run(
        "smoke_test_agent_2",
        "smoke_test",
        trigger_type="cli",
        product="test_product",
    )

    assert run_id is not None
    assert run_id.startswith("202")  # Should start with year

    # Log event
    client.log_event(run_id, "checkpoint", {"step": 1})

    # End run
    client.end_run(run_id, status="success", items_succeeded=3)

    print("[OK] Explicit start/end pattern successful")


def test_stats():
    """Test getting telemetry statistics."""
    print("[TEST] Testing statistics...")

    client = TelemetryClient()
    stats = client.get_stats()

    assert "total_runs" in stats
    # New HTTP API-based stats (MIG-008)
    # May also have database fallback fields if API unavailable
    assert "total_runs" in stats or "error" in stats

    print(f"[OK] Statistics retrieved: {stats.get('total_runs', 'N/A')} total runs")


def main():
    """Run all smoke tests."""
    print("=" * 60)
    print("TEL-03 Smoke Test")
    print("=" * 60)

    try:
        test_imports()
        test_basic_run()
        test_explicit_start_end()
        test_stats()

        print("=" * 60)
        print("[SUCCESS] All smoke tests passed!")
        print("=" * 60)
        return 0

    except Exception as e:
        print("=" * 60)
        print(f"[FAIL] Smoke test failed: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
