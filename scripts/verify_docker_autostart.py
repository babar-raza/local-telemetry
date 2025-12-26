#!/usr/bin/env python3
"""
Verify Docker container auto-start after Docker Desktop restart.

This script polls for the container to become healthy after Docker Desktop
starts/restarts, verifying the restart:always policy is working.

Usage:
    1. Close Docker Desktop completely
    2. Reopen Docker Desktop
    3. Run: python scripts/verify_docker_autostart.py

The script will poll for up to 120 seconds for the container to become healthy.
"""
import subprocess
import time
import sys

CONTAINER_NAME = "local-telemetry-api"
TIMEOUT = 120  # seconds
POLL_INTERVAL = 5  # seconds


def check_container_status():
    """Get container status."""
    result = subprocess.run(
        ["docker", "ps", "--filter", f"name={CONTAINER_NAME}", "--format", "{{.Status}}"],
        capture_output=True, text=True
    )
    return result.stdout.strip()


def check_health_endpoint():
    """Check if API health endpoint responds."""
    try:
        import requests
        resp = requests.get("http://localhost:8765/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def main():
    print("=" * 60)
    print("DOCKER AUTO-START VERIFICATION")
    print("=" * 60)
    print(f"Container: {CONTAINER_NAME}")
    print(f"Timeout: {TIMEOUT}s")
    print()
    print("Prerequisites:")
    print("  1. Docker Desktop was just started/restarted")
    print("  2. Container was previously running with restart:always")
    print()
    print("Polling for container status...")
    print()

    start_time = time.time()
    last_status = None

    while time.time() - start_time < TIMEOUT:
        elapsed = time.time() - start_time

        # Check container status
        status = check_container_status()

        if status != last_status:
            if status:
                print(f"[{elapsed:5.1f}s] Container status: {status}")
            else:
                print(f"[{elapsed:5.1f}s] Container not found (Docker may still be starting)")
            last_status = status

        # Check if healthy
        if "healthy" in status.lower():
            print()
            print(f"[PASS] Container became healthy after {elapsed:.1f}s")

            # Also verify API responds
            if check_health_endpoint():
                print("[PASS] API health endpoint responding")
                print()
                print("=" * 60)
                print("VERIFICATION SUCCESSFUL")
                print("=" * 60)
                print()
                print("The container auto-started correctly after Docker Desktop restart.")
                print("The restart:always policy is working as expected.")
                return 0
            else:
                print("[WARN] Container healthy but API not yet responding")

        elif "starting" in status.lower() or "up" in status.lower():
            # Container is starting, wait
            pass

        time.sleep(POLL_INTERVAL)

    # Timeout
    print()
    print(f"[FAIL] Container did not become healthy within {TIMEOUT}s")
    print()
    print("Troubleshooting:")
    print("  1. Check Docker Desktop is fully started")
    print("  2. Run: docker logs local-telemetry-api")
    print("  3. Verify restart policy: docker inspect local-telemetry-api --format='{{.HostConfig.RestartPolicy.Name}}'")
    return 1


if __name__ == "__main__":
    sys.exit(main())
