#!/usr/bin/env python3
"""
Tests for db_archive_to_sheets.py

Tests the archival script's core functionality:
- SQL query building
- Aggregation logic
- Payload formatting
- Deletion safety
"""

import pytest
import sys
import sqlite3
import tempfile
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from db_archive_to_sheets import (
    build_aggregation_query,
    GROUP_COLUMNS,
    VALID_GROUP_OPTIONS,
    AggregatedSummary,
    summary_to_sheets_payload,
    query_aggregated_summaries,
    count_archivable_records,
    delete_archived_records,
)


class TestBuildAggregationQuery:
    """Test dynamic SQL query building."""

    def test_default_grouping(self):
        """Test default grouping by date, agent, job_type."""
        query = build_aggregation_query(['date', 'agent', 'job_type'], 7)

        assert "date(created_at) AS date" in query
        assert "agent_name AS agent" in query
        assert "job_type AS job_type" in query
        assert "GROUP BY date(created_at), agent_name, job_type" in query
        assert "-7 days" in query

    def test_subdomain_grouping(self):
        """Test grouping by subdomain."""
        query = build_aggregation_query(['date', 'subdomain'], 14)

        assert "website_section AS subdomain" in query
        assert "GROUP BY date(created_at), website_section" in query
        assert "-14 days" in query

    def test_product_grouping(self):
        """Test grouping by product."""
        query = build_aggregation_query(['date', 'product'], 30)

        assert "product AS product" in query
        assert "GROUP BY date(created_at), product" in query
        assert "-30 days" in query

    def test_all_aggregation_columns_present(self):
        """Test all aggregation columns are in query."""
        query = build_aggregation_query(['date'], 7)

        assert "COUNT(*) AS total_count" in query
        assert "success_count" in query
        assert "failure_count" in query
        assert "other_count" in query
        assert "avg_duration_ms" in query
        assert "total_discovered" in query
        assert "total_succeeded" in query
        assert "total_failed" in query
        assert "total_skipped" in query
        assert "GROUP_CONCAT(event_id) AS event_ids" in query


class TestAggregatedSummary:
    """Test AggregatedSummary dataclass."""

    def test_success_rate_calculation(self):
        """Test success rate is calculated correctly."""
        summary = AggregatedSummary(
            group_keys={'date': '2026-01-01', 'agent': 'test'},
            total_count=100,
            success_count=85,
            failure_count=10,
            other_count=5,
            avg_duration_ms=1000.0,
            total_discovered=500,
            total_succeeded=450,
            total_failed=50,
            total_skipped=0,
            event_ids=['id1', 'id2'],
        )

        assert summary.success_rate == 85.0

    def test_success_rate_zero_total(self):
        """Test success rate with zero total count."""
        summary = AggregatedSummary(
            group_keys={},
            total_count=0,
            success_count=0,
            failure_count=0,
            other_count=0,
            avg_duration_ms=0,
            total_discovered=0,
            total_succeeded=0,
            total_failed=0,
            total_skipped=0,
            event_ids=[],
        )

        assert summary.success_rate == 0.0


class TestSummaryToSheetsPayload:
    """Test payload formatting for Google Sheets API."""

    def test_basic_payload_structure(self):
        """Test payload has all required fields."""
        summary = AggregatedSummary(
            group_keys={'date': '2026-01-01', 'agent': 'test_agent'},
            total_count=100,
            success_count=90,
            failure_count=8,
            other_count=2,
            avg_duration_ms=1500.0,
            total_discovered=500,
            total_succeeded=480,
            total_failed=20,
            total_skipped=0,
            event_ids=['id1', 'id2'],
        )

        payload = summary_to_sheets_payload(summary, ['date', 'agent'])

        assert 'timestamp' in payload
        assert payload['agent_name'] == 'test_agent'
        assert payload['job_type'] == 'aggregated_daily_archive'
        assert payload['items_discovered'] == 100
        assert payload['items_succeeded'] == 90
        assert payload['items_failed'] == 8
        assert payload['items_skipped'] == 2

    def test_item_name_format(self):
        """Test item_name includes group keys."""
        summary = AggregatedSummary(
            group_keys={'date': '2026-01-05', 'agent': 'my_agent'},
            total_count=50,
            success_count=50,
            failure_count=0,
            other_count=0,
            avg_duration_ms=0,
            total_discovered=0,
            total_succeeded=0,
            total_failed=0,
            total_skipped=0,
            event_ids=[],
        )

        payload = summary_to_sheets_payload(summary, ['date', 'agent'])

        assert 'archive_' in payload['item_name']
        assert 'date=2026-01-05' in payload['item_name']
        assert 'agent=my_agent' in payload['item_name']


class TestDatabaseOperations:
    """Test database operations with in-memory SQLite."""

    @pytest.fixture
    def test_db(self):
        """Create a test database with sample data."""
        conn = sqlite3.connect(':memory:')
        cursor = conn.cursor()

        # Create minimal agent_runs table
        cursor.execute("""
            CREATE TABLE agent_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE,
                agent_name TEXT,
                job_type TEXT,
                status TEXT,
                duration_ms INTEGER,
                items_discovered INTEGER,
                items_succeeded INTEGER,
                items_failed INTEGER,
                items_skipped INTEGER,
                website_section TEXT,
                product TEXT,
                website TEXT,
                created_at TEXT
            )
        """)

        # Insert test data (some old, some recent)
        old_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d %H:%M:%S')
        recent_date = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')

        test_data = [
            ('evt1', 'agent_a', 'job1', 'success', 100, 10, 10, 0, 0, 'docs', 'prod1', 'example.com', old_date),
            ('evt2', 'agent_a', 'job1', 'success', 150, 20, 18, 2, 0, 'docs', 'prod1', 'example.com', old_date),
            ('evt3', 'agent_a', 'job2', 'failure', 200, 5, 0, 5, 0, 'api', 'prod1', 'example.com', old_date),
            ('evt4', 'agent_b', 'job1', 'success', 50, 15, 15, 0, 0, 'docs', 'prod2', 'test.com', old_date),
            ('evt5', 'agent_a', 'job1', 'success', 100, 10, 10, 0, 0, 'docs', 'prod1', 'example.com', recent_date),
        ]

        cursor.executemany("""
            INSERT INTO agent_runs
            (event_id, agent_name, job_type, status, duration_ms,
             items_discovered, items_succeeded, items_failed, items_skipped,
             website_section, product, website, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, test_data)

        conn.commit()
        yield conn
        conn.close()

    def test_count_archivable_records(self, test_db):
        """Test counting records older than threshold."""
        cursor = test_db.cursor()

        # 4 records are older than 7 days, 1 is recent
        count = count_archivable_records(cursor, 7)
        assert count == 4

    def test_query_aggregated_summaries(self, test_db):
        """Test aggregation query returns correct summaries."""
        cursor = test_db.cursor()

        summaries = query_aggregated_summaries(cursor, ['agent', 'job_type'], 7)

        # Should have 3 groups: (agent_a, job1), (agent_a, job2), (agent_b, job1)
        assert len(summaries) == 3

        # Find agent_a/job1 summary
        a_job1 = next(s for s in summaries
                      if s.group_keys.get('agent') == 'agent_a'
                      and s.group_keys.get('job_type') == 'job1')

        assert a_job1.total_count == 2  # evt1, evt2
        assert a_job1.success_count == 2
        assert a_job1.failure_count == 0
        assert len(a_job1.event_ids) == 2
        assert 'evt1' in a_job1.event_ids
        assert 'evt2' in a_job1.event_ids

    def test_delete_archived_records(self, test_db):
        """Test deletion only removes specified event_ids."""
        cursor = test_db.cursor()

        # Count before
        cursor.execute("SELECT COUNT(*) FROM agent_runs")
        count_before = cursor.fetchone()[0]
        assert count_before == 5

        # Delete two records
        deleted = delete_archived_records(test_db, ['evt1', 'evt2'])
        assert deleted == 2

        # Count after
        cursor.execute("SELECT COUNT(*) FROM agent_runs")
        count_after = cursor.fetchone()[0]
        assert count_after == 3

        # Verify correct records remain
        cursor.execute("SELECT event_id FROM agent_runs ORDER BY event_id")
        remaining = [row[0] for row in cursor.fetchall()]
        assert remaining == ['evt3', 'evt4', 'evt5']


class TestGroupByValidation:
    """Test group-by option validation."""

    def test_valid_options(self):
        """Test all valid options are in GROUP_COLUMNS."""
        for opt in VALID_GROUP_OPTIONS:
            assert opt in GROUP_COLUMNS

    def test_column_mapping(self):
        """Test column mappings are correct."""
        assert GROUP_COLUMNS['date'] == 'date(created_at)'
        assert GROUP_COLUMNS['agent'] == 'agent_name'
        assert GROUP_COLUMNS['job_type'] == 'job_type'
        assert GROUP_COLUMNS['subdomain'] == 'website_section'
        assert GROUP_COLUMNS['product'] == 'product'
        assert GROUP_COLUMNS['website'] == 'website'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
