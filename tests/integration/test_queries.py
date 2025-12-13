"""
Integration tests for querying telemetry data from SQLite.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from telemetry import TelemetryClient, TelemetryConfig


@pytest.fixture
def telemetry_client():
    """Create client and seed test data."""
    config = TelemetryConfig.from_env()
    client = TelemetryClient(config)

    # Seed some test data
    for i in range(5):
        with client.track_run(
            agent_name=f"query_test_agent_{i % 2}",  # 2 different agents
            job_type=f"query_test_job_{i}",
            trigger_type="test"
        ) as run_ctx:
            run_ctx.set_metrics(
                items_discovered=10 + i,
                items_succeeded=8 + i,
                items_failed=2
            )
            run_ctx.log_event("test_event", {"step": i})

    return client


class TestQueries:
    """Test querying telemetry data."""

    def test_query_all_runs(self, telemetry_client):
        """Test querying all runs."""
        config = TelemetryConfig.from_env()
        conn = sqlite3.connect(str(config.database_path))
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM agent_runs")
        count = cursor.fetchone()[0]

        assert count >= 5, f"Expected at least 5 runs, got {count}"
        conn.close()

    def test_query_by_agent_name(self, telemetry_client):
        """Test filtering by agent name."""
        config = TelemetryConfig.from_env()
        conn = sqlite3.connect(str(config.database_path))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM agent_runs
            WHERE agent_name LIKE 'query_test_agent%'
        """)
        count = cursor.fetchone()[0]

        assert count >= 5
        conn.close()

    def test_query_by_specific_agent(self, telemetry_client):
        """Test filtering by specific agent."""
        config = TelemetryConfig.from_env()
        conn = sqlite3.connect(str(config.database_path))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM agent_runs
            WHERE agent_name = 'query_test_agent_0'
        """)
        count = cursor.fetchone()[0]

        # Should have 3 runs (indices 0, 2, 4 from the loop)
        assert count >= 3
        conn.close()

    def test_query_aggregate_metrics(self, telemetry_client):
        """Test aggregating metrics."""
        config = TelemetryConfig.from_env()
        conn = sqlite3.connect(str(config.database_path))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                SUM(items_discovered) as total_discovered,
                SUM(items_succeeded) as total_succeeded,
                SUM(items_failed) as total_failed
            FROM agent_runs
            WHERE agent_name LIKE 'query_test_agent%'
        """)

        row = cursor.fetchone()
        # Sum of 10+11+12+13+14 = 60
        assert row[0] >= 60
        # Sum of 8+9+10+11+12 = 50
        assert row[1] >= 50
        # 2*5 = 10
        assert row[2] >= 10

        conn.close()

    def test_query_average_metrics(self, telemetry_client):
        """Test averaging metrics."""
        config = TelemetryConfig.from_env()
        conn = sqlite3.connect(str(config.database_path))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                AVG(items_discovered) as avg_discovered,
                AVG(duration_ms) as avg_duration
            FROM agent_runs
            WHERE agent_name LIKE 'query_test_agent%'
            AND items_discovered IS NOT NULL
        """)

        row = cursor.fetchone()
        # Average of 10+11+12+13+14 = 12
        assert row[0] >= 11.0 and row[0] <= 13.0

        conn.close()

    def test_query_by_status(self, telemetry_client):
        """Test filtering by status."""
        config = TelemetryConfig.from_env()
        conn = sqlite3.connect(str(config.database_path))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM agent_runs
            WHERE agent_name LIKE 'query_test_agent%'
            AND status = 'success'
        """)
        success_count = cursor.fetchone()[0]

        # All test runs should succeed
        assert success_count >= 5

        cursor.execute("""
            SELECT COUNT(*) FROM agent_runs
            WHERE agent_name LIKE 'query_test_agent%'
            AND status = 'failed'
        """)
        failed_count = cursor.fetchone()[0]

        # No test runs should fail
        assert failed_count == 0

        conn.close()

    def test_query_by_time_range(self, telemetry_client):
        """Test querying by time range."""
        config = TelemetryConfig.from_env()
        conn = sqlite3.connect(str(config.database_path))
        cursor = conn.cursor()

        # Get runs from last hour
        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        cursor.execute("""
            SELECT COUNT(*) FROM agent_runs
            WHERE start_time >= ?
            AND agent_name LIKE 'query_test_agent%'
        """, (one_hour_ago,))

        count = cursor.fetchone()[0]
        assert count >= 5

        conn.close()

    def test_query_recent_runs(self, telemetry_client):
        """Test querying recent runs with ordering."""
        config = TelemetryConfig.from_env()
        conn = sqlite3.connect(str(config.database_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT run_id, agent_name, job_type, start_time
            FROM agent_runs
            WHERE agent_name LIKE 'query_test_agent%'
            ORDER BY start_time DESC
            LIMIT 10
        """)

        rows = cursor.fetchall()
        assert len(rows) >= 5

        # Verify ordering (newest first)
        if len(rows) >= 2:
            assert rows[0]['start_time'] >= rows[1]['start_time']

        conn.close()

    def test_query_by_job_type(self, telemetry_client):
        """Test filtering by job type."""
        config = TelemetryConfig.from_env()
        conn = sqlite3.connect(str(config.database_path))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(DISTINCT job_type) FROM agent_runs
            WHERE agent_name LIKE 'query_test_agent%'
        """)
        distinct_jobs = cursor.fetchone()[0]

        # Should have 5 distinct job types
        assert distinct_jobs >= 5

        conn.close()

    def test_query_with_metrics_filter(self, telemetry_client):
        """Test filtering by metric values."""
        config = TelemetryConfig.from_env()
        conn = sqlite3.connect(str(config.database_path))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM agent_runs
            WHERE agent_name LIKE 'query_test_agent%'
            AND items_discovered >= 12
        """)
        count = cursor.fetchone()[0]

        # Runs with indices 2, 3, 4 have items_discovered >= 12
        assert count >= 3

        conn.close()

    def test_query_group_by_agent(self, telemetry_client):
        """Test grouping results by agent."""
        config = TelemetryConfig.from_env()
        conn = sqlite3.connect(str(config.database_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                agent_name,
                COUNT(*) as run_count,
                SUM(items_discovered) as total_items
            FROM agent_runs
            WHERE agent_name LIKE 'query_test_agent%'
            GROUP BY agent_name
            ORDER BY run_count DESC
        """)

        rows = cursor.fetchall()
        assert len(rows) >= 2  # We have 2 different agents

        for row in rows:
            assert row['run_count'] >= 2
            assert row['total_items'] >= 10

        conn.close()

    def test_query_with_null_checks(self, telemetry_client):
        """Test handling of NULL values in queries."""
        config = TelemetryConfig.from_env()
        conn = sqlite3.connect(str(config.database_path))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM agent_runs
            WHERE agent_name LIKE 'query_test_agent%'
            AND end_time IS NOT NULL
        """)
        completed_count = cursor.fetchone()[0]

        # All test runs should be completed
        assert completed_count >= 5

        cursor.execute("""
            SELECT COUNT(*) FROM agent_runs
            WHERE agent_name LIKE 'query_test_agent%'
            AND error_summary IS NULL
        """)
        no_error_count = cursor.fetchone()[0]

        # All test runs should have no errors
        assert no_error_count >= 5

        conn.close()

    def test_query_duration_calculation(self, telemetry_client):
        """Test querying duration metrics."""
        config = TelemetryConfig.from_env()
        conn = sqlite3.connect(str(config.database_path))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                MIN(duration_ms) as min_duration,
                MAX(duration_ms) as max_duration,
                AVG(duration_ms) as avg_duration
            FROM agent_runs
            WHERE agent_name LIKE 'query_test_agent%'
            AND duration_ms IS NOT NULL
        """)

        row = cursor.fetchone()
        # Durations should be reasonable (> 0, < 1 hour)
        if row[0] is not None:
            assert row[0] >= 0  # min
            assert row[1] < 3600000  # max (1 hour in ms)
            assert row[2] >= 0  # avg

        conn.close()

    def test_complex_query_with_multiple_conditions(self, telemetry_client):
        """Test complex query with multiple conditions."""
        config = TelemetryConfig.from_env()
        conn = sqlite3.connect(str(config.database_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        cursor.execute("""
            SELECT
                run_id,
                agent_name,
                job_type,
                items_discovered,
                items_succeeded,
                status
            FROM agent_runs
            WHERE agent_name LIKE 'query_test_agent%'
            AND status = 'success'
            AND start_time >= ?
            AND items_discovered >= 10
            ORDER BY items_discovered DESC
            LIMIT 5
        """, (one_hour_ago,))

        rows = cursor.fetchall()
        assert len(rows) >= 5

        # Verify all conditions met
        for row in rows:
            assert 'query_test_agent' in row['agent_name']
            assert row['status'] == 'success'
            assert row['items_discovered'] >= 10

        conn.close()
