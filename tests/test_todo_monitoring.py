"""
Tests for TodoWrite update monitoring.

Tests detection of batched updates and timing analysis.
"""

import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from todo_update_monitor import (
    parse_update_log,
    detect_batched_updates,
    analyze_update_timing,
    TodoUpdate,
    BatchEvent
)


@pytest.fixture
def temp_log_file():
    """Create temporary log file."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)


class TestLogParsing:
    """Tests for update log parsing."""

    def test_parse_single_update(self, temp_log_file):
        """Test parsing single update."""
        log_content = "2025-12-11 14:30:22 - Task: task-1, Status: pending → in_progress\n"
        temp_log_file.write_text(log_content)

        updates = parse_update_log(temp_log_file)

        assert len(updates) == 1
        assert updates[0].task_id == "task-1"
        assert updates[0].old_status == "pending"
        assert updates[0].new_status == "in_progress"

    def test_parse_multiple_updates(self, temp_log_file):
        """Test parsing multiple updates."""
        log_content = """
2025-12-11 14:30:22 - Task: task-1, Status: pending → in_progress
2025-12-11 14:35:10 - Task: task-1, Status: in_progress → completed
2025-12-11 14:40:05 - Task: task-2, Status: pending → in_progress
"""
        temp_log_file.write_text(log_content)

        updates = parse_update_log(temp_log_file)

        assert len(updates) == 3
        assert updates[0].task_id == "task-1"
        assert updates[2].task_id == "task-2"

    def test_parse_empty_log(self, temp_log_file):
        """Test parsing empty log."""
        temp_log_file.write_text("")

        updates = parse_update_log(temp_log_file)

        assert len(updates) == 0

    def test_parse_malformed_lines(self, temp_log_file):
        """Test that malformed lines are skipped."""
        log_content = """
Invalid line without timestamp
2025-12-11 14:30:22 - Task: task-1, Status: pending → in_progress
Another invalid line
"""
        temp_log_file.write_text(log_content)

        updates = parse_update_log(temp_log_file)

        assert len(updates) == 1


class TestBatchingDetection:
    """Tests for batched update detection."""

    def test_no_batching_detected(self):
        """Test when updates are properly spaced."""
        base_time = datetime(2025, 12, 11, 14, 0, 0)
        updates = [
            TodoUpdate(base_time, "task-1", "pending", "in_progress", 1),
            TodoUpdate(base_time + timedelta(minutes=5), "task-2", "pending", "in_progress", 2),
            TodoUpdate(base_time + timedelta(minutes=10), "task-3", "pending", "in_progress", 3)
        ]

        batches = detect_batched_updates(updates, threshold_seconds=60)

        assert len(batches) == 0

    def test_simple_batch_detected(self):
        """Test detection of simple batch (2 updates within threshold)."""
        base_time = datetime(2025, 12, 11, 14, 0, 0)
        updates = [
            TodoUpdate(base_time, "task-1", "pending", "completed", 1),
            TodoUpdate(base_time + timedelta(seconds=2), "task-2", "pending", "completed", 2)
        ]

        batches = detect_batched_updates(updates, threshold_seconds=5)

        assert len(batches) == 1
        assert batches[0].task_count == 2

    def test_multiple_batches_detected(self):
        """Test detection of multiple separate batches."""
        base_time = datetime(2025, 12, 11, 14, 0, 0)
        updates = [
            # Batch 1
            TodoUpdate(base_time, "task-1", "pending", "completed", 1),
            TodoUpdate(base_time + timedelta(seconds=2), "task-2", "pending", "completed", 2),
            # Gap
            TodoUpdate(base_time + timedelta(minutes=10), "task-3", "pending", "in_progress", 3),
            # Batch 2
            TodoUpdate(base_time + timedelta(minutes=15), "task-4", "pending", "completed", 4),
            TodoUpdate(base_time + timedelta(minutes=15, seconds=3), "task-5", "pending", "completed", 5)
        ]

        batches = detect_batched_updates(updates, threshold_seconds=5)

        assert len(batches) == 2
        assert batches[0].task_count == 2
        assert batches[1].task_count == 2

    def test_large_batch_detected(self):
        """Test detection of large batch (many updates)."""
        base_time = datetime(2025, 12, 11, 14, 0, 0)
        updates = [
            TodoUpdate(base_time + timedelta(seconds=i), f"task-{i}", "pending", "completed", i)
            for i in range(10)
        ]

        batches = detect_batched_updates(updates, threshold_seconds=5)

        assert len(batches) == 1
        assert batches[0].task_count == 10

    def test_custom_threshold(self):
        """Test batching with custom threshold."""
        base_time = datetime(2025, 12, 11, 14, 0, 0)
        updates = [
            TodoUpdate(base_time, "task-1", "pending", "completed", 1),
            TodoUpdate(base_time + timedelta(seconds=15), "task-2", "pending", "completed", 2)
        ]

        # With 5 second threshold: no batch
        batches_5s = detect_batched_updates(updates, threshold_seconds=5)
        assert len(batches_5s) == 0

        # With 20 second threshold: batch detected
        batches_20s = detect_batched_updates(updates, threshold_seconds=20)
        assert len(batches_20s) == 1


class TestTimingAnalysis:
    """Tests for timing analysis."""

    def test_timing_single_update(self):
        """Test timing analysis with single update."""
        updates = [
            TodoUpdate(datetime(2025, 12, 11, 14, 0, 0), "task-1", "pending", "completed", 1)
        ]

        analysis = analyze_update_timing(updates)

        assert analysis['total_updates'] == 1
        assert analysis['time_span_hours'] == 0

    def test_timing_multiple_updates(self):
        """Test timing analysis with multiple updates."""
        base_time = datetime(2025, 12, 11, 14, 0, 0)
        updates = [
            TodoUpdate(base_time, "task-1", "pending", "in_progress", 1),
            TodoUpdate(base_time + timedelta(minutes=30), "task-2", "pending", "in_progress", 2),
            TodoUpdate(base_time + timedelta(hours=1), "task-3", "pending", "in_progress", 3)
        ]

        analysis = analyze_update_timing(updates)

        assert analysis['total_updates'] == 3
        assert analysis['time_span_hours'] == 1.0
        assert analysis['avg_update_interval_seconds'] > 0

    def test_timing_empty_updates(self):
        """Test timing analysis with no updates."""
        analysis = analyze_update_timing([])

        assert analysis['total_updates'] == 0
        assert analysis['time_span_hours'] == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
