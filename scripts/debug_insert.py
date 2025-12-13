"""
Quick debug script to test insert_run
"""
import sys
import sqlite3
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from telemetry.database import DatabaseWriter
from telemetry.models import RunRecord, get_iso8601_timestamp
from telemetry.schema import create_schema

# Create temp database
with tempfile.TemporaryDirectory() as tmp:
    db_path = Path(tmp) / "test.sqlite"

    # Setup database with schema
    print(f"Creating database at: {db_path}")
    success, messages = create_schema(str(db_path))
    print(f"Schema creation: {success}")
    for msg in messages:
        print(f"  {msg}")

    # Create writer
    writer = DatabaseWriter(db_path)
    print("DatabaseWriter created")

    # Create record
    record = RunRecord(
        run_id="test-run-123",
        agent_name="test_agent",
        job_type="test_job",
        trigger_type="cli",
        start_time=get_iso8601_timestamp(),
        status="running",
    )
    print(f"Record created: {record.run_id}")

    # Try insert
    print("\nAttempting insert...")
    success, message = writer.insert_run(record)

    print(f"\nRESULT:")
    print(f"  Success: {success}")
    print(f"  Message: {message}")

    if success:
        print("\n[OK] INSERT SUCCEEDED")

        # Verify retrieval
        retrieved = writer.get_run("test-run-123")
        if retrieved:
            print(f"[OK] Retrieved record: {retrieved.run_id}")
        else:
            print("[FAIL] Could not retrieve record")
    else:
        print(f"\n[FAIL] INSERT FAILED: {message}")
