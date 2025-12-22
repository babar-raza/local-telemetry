#!/usr/bin/env python3
"""
Quick deployment test script.

Tests:
1. Import all required modules
2. Verify configuration loads
3. Test telemetry service can be imported
4. Simulate a simple startup check
"""

import sys
import os
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, r"C:\Users\prora\AppData\Roaming\Python\Python313\site-packages")

print("=" * 70)
print("DEPLOYMENT TEST")
print("=" * 70)
print()

# Test 1: Import FastAPI and Uvicorn
print("[Test 1] Checking FastAPI and Uvicorn...")
try:
    import fastapi
    import uvicorn
    print(f"  [OK] FastAPI {fastapi.__version__}")
    print(f"  [OK] Uvicorn {uvicorn.__version__}")
except ImportError as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

# Test 2: Import telemetry modules
print()
print("[Test 2] Importing telemetry modules...")
try:
    from telemetry.config import TelemetryAPIConfig
    from telemetry.single_writer_guard import SingleWriterGuard
    print("  [OK] TelemetryAPIConfig imported")
    print("  [OK] SingleWriterGuard imported")
except ImportError as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

# Test 3: Import telemetry service
print()
print("[Test 3] Importing telemetry_service...")
try:
    # Change to project root for import
    os.chdir(project_root)
    import telemetry_service
    print("  [OK] telemetry_service imported")
    print(f"  [OK] FastAPI app created: {telemetry_service.app.title}")
except Exception as e:
    print(f"  [FAIL] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Verify configuration
print()
print("[Test 4] Checking configuration...")
try:
    print(f"  DB Path: {TelemetryAPIConfig.DB_PATH}")
    print(f"  API Port: {TelemetryAPIConfig.API_PORT}")
    print(f"  Journal Mode: {TelemetryAPIConfig.DB_JOURNAL_MODE}")
    print(f"  Synchronous: {TelemetryAPIConfig.DB_SYNCHRONOUS}")
    print(f"  Workers: {TelemetryAPIConfig.API_WORKERS}")

    if TelemetryAPIConfig.API_WORKERS != 1:
        print("  [WARN] API_WORKERS should be 1 for single-writer")
    else:
        print("  [OK] API_WORKERS correctly set to 1")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

# Test 5: Check schema file exists
print()
print("[Test 5] Checking schema file...")
schema_file = project_root / "schema" / "telemetry_v6.sql"
if schema_file.exists():
    print(f"  [OK] Schema file found: {schema_file}")
else:
    print(f"  [FAIL] Schema file not found: {schema_file}")
    sys.exit(1)

# Test 6: Check migration script exists
print()
print("[Test 6] Checking migration script...")
migration_script = project_root / "scripts" / "migrate_v5_to_v6.py"
if migration_script.exists():
    print(f"  [OK] Migration script found: {migration_script}")
else:
    print(f"  [FAIL] Migration script not found: {migration_script}")
    sys.exit(1)

print()
print("=" * 70)
print("[SUCCESS] All deployment tests passed!")
print("=" * 70)
print()
print("Next steps:")
print("1. Start the service:")
print("   python telemetry_service.py")
print()
print("2. Test health endpoint:")
print("   curl http://localhost:8765/health")
print()
print("3. Test creating a run:")
print("   curl -X POST http://localhost:8765/api/v1/runs \\")
print("     -H \"Content-Type: application/json\" \\")
print("     -d '{...}'")
print("=" * 70)
