"""
Manual validation script for GT-01: Automatic Git Detection Helper

This script performs 5 manual validation scenarios:
1. Detection in a Git repository (current directory)
2. Detection with caching (performance test)
3. Force refresh
4. Disabled auto-detection
5. Clear cache and re-detect

Run this in the local-telemetry directory to verify Git detection works.
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from telemetry.git_detector import GitDetector


def print_section(title):
    """Print section header."""
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print(f"{'=' * 60}\n")


def scenario_1_basic_detection():
    """Test 1: Basic detection in Git repository."""
    print_section("Scenario 1: Basic Git Detection")

    detector = GitDetector()
    context = detector.get_git_context()

    print(f"Working directory: {detector.working_dir}")
    print(f"Auto-detect enabled: {detector.auto_detect}")
    print(f"\nDetected Git context:")
    for key, value in context.items():
        print(f"  {key}: {value}")

    if not context:
        print("  (No Git repository detected)")

    return context


def scenario_2_caching_performance():
    """Test 2: Caching performance (second call should be instant)."""
    print_section("Scenario 2: Caching Performance Test")

    detector = GitDetector()

    # First call (with subprocess)
    start1 = time.time()
    context1 = detector.get_git_context()
    duration1 = time.time() - start1

    # Second call (cached, no subprocess)
    start2 = time.time()
    context2 = detector.get_git_context()
    duration2 = time.time() - start2

    print(f"First call duration: {duration1*1000:.2f} ms")
    print(f"Second call duration: {duration2*1000:.2f} ms")
    print(f"Performance improvement: {(duration1/duration2):.1f}x faster (cached)")

    # Verify results are identical
    assert context1 == context2, "Cached result should match first result"
    print(f"\nCached result matches: {context1 == context2}")

    return duration1, duration2


def scenario_3_force_refresh():
    """Test 3: Force refresh bypasses cache."""
    print_section("Scenario 3: Force Refresh")

    detector = GitDetector()

    # First call (populates cache)
    context1 = detector.get_git_context()
    print("Initial detection (cached):")
    print(f"  {context1}")

    # Force refresh (bypasses cache)
    context2 = detector.get_git_context(force_refresh=True)
    print("\nForce refresh detection:")
    print(f"  {context2}")

    # Results should be identical
    assert context1 == context2, "Force refresh should return same result"
    print(f"\nResults match: {context1 == context2}")


def scenario_4_disabled_auto_detection():
    """Test 4: auto_detect=False prevents detection."""
    print_section("Scenario 4: Disabled Auto-Detection")

    detector = GitDetector(auto_detect=False)
    context = detector.get_git_context()

    print(f"Auto-detect enabled: {detector.auto_detect}")
    print(f"Detected context: {context}")
    print(f"Context is empty: {context == {}}")

    assert context == {}, "Disabled auto-detect should return empty dict"


def scenario_5_clear_cache():
    """Test 5: Clear cache and re-detect."""
    print_section("Scenario 5: Clear Cache and Re-detect")

    detector = GitDetector()

    # First call
    context1 = detector.get_git_context()
    print("Initial detection:")
    print(f"  {context1}")

    # Clear cache
    detector.clear_cache()
    print("\nCache cleared")

    # Next call should re-detect
    context2 = detector.get_git_context()
    print("\nRe-detected after cache clear:")
    print(f"  {context2}")

    # Results should be identical
    assert context1 == context2, "Re-detection should return same result"
    print(f"\nResults match: {context1 == context2}")


def main():
    """Run all validation scenarios."""
    print("\n" + "=" * 60)
    print(" GT-01 Manual Validation Tests")
    print(" Automatic Git Detection Helper")
    print("=" * 60)

    try:
        # Run all scenarios
        context = scenario_1_basic_detection()
        duration1, duration2 = scenario_2_caching_performance()
        scenario_3_force_refresh()
        scenario_4_disabled_auto_detection()
        scenario_5_clear_cache()

        # Summary
        print_section("VALIDATION SUMMARY")
        print("All 5 scenarios completed successfully!")
        print(f"\nDetected Git context:")
        for key, value in context.items():
            print(f"  {key}: {value}")

        if not context:
            print("  (No Git repository detected - this is expected if not in a Git repo)")

        print(f"\nPerformance:")
        print(f"  First call: {duration1*1000:.2f} ms")
        print(f"  Cached call: {duration2*1000:.2f} ms")
        print(f"  Improvement: {(duration1/duration2):.1f}x faster")

        print("\n" + "=" * 60)
        print(" SUCCESS: All validation tests passed!")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\nERROR: Validation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
