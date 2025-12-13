"""
Tests for verified TodoWrite update functionality.

Tests the wrapper that verifies deliverables before allowing TodoWrite completion.
"""

import json
import pytest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from verified_todo_update import (
    verify_deliverables_exist,
    run_quality_gate_verification,
    update_todo_if_verified,
    parse_task_spec_for_deliverables,
    main
)


@pytest.fixture
def temp_project():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)

        # Create sample deliverable files
        (project_root / "scripts").mkdir()
        (project_root / "scripts" / "sample.py").write_text("# Sample\n" * 100)

        (project_root / "docs").mkdir()
        (project_root / "docs" / "README.md").write_text("# Docs\n" * 50)

        yield project_root


@pytest.fixture
def sample_task_spec(temp_project):
    """Create a sample task specification."""
    spec_content = """
# Sample Task

**Deliverables**:
1. **scripts/sample.py** (80-120 lines)
   - Main implementation
2. **docs/README.md** (40-60 lines)
   - Documentation
"""
    spec_path = temp_project / "task_spec.md"
    spec_path.write_text(spec_content)
    return spec_path


class TestDeliverableExistence:
    """Tests for deliverable existence checking."""

    def test_all_deliverables_exist(self, temp_project):
        """Test when all deliverables exist."""
        deliverables = [
            {'file': 'scripts/sample.py'},
            {'file': 'docs/README.md'}
        ]

        all_exist, missing = verify_deliverables_exist(deliverables, temp_project)

        assert all_exist is True
        assert len(missing) == 0

    def test_some_deliverables_missing(self, temp_project):
        """Test when some deliverables are missing."""
        deliverables = [
            {'file': 'scripts/sample.py'},
            {'file': 'docs/missing.md'}
        ]

        all_exist, missing = verify_deliverables_exist(deliverables, temp_project)

        assert all_exist is False
        assert len(missing) == 1
        assert 'docs/missing.md' in missing

    def test_all_deliverables_missing(self, temp_project):
        """Test when all deliverables are missing."""
        deliverables = [
            {'file': 'missing1.py'},
            {'file': 'missing2.md'}
        ]

        all_exist, missing = verify_deliverables_exist(deliverables, temp_project)

        assert all_exist is False
        assert len(missing) == 2

    def test_empty_deliverables_list(self, temp_project):
        """Test with empty deliverables list."""
        all_exist, missing = verify_deliverables_exist([], temp_project)

        assert all_exist is True
        assert len(missing) == 0


class TestTaskSpecParsing:
    """Tests for task spec deliverable parsing."""

    def test_parse_deliverables_from_spec(self, sample_task_spec):
        """Test parsing deliverables from task spec."""
        deliverables = parse_task_spec_for_deliverables(sample_task_spec)

        assert len(deliverables) == 2
        assert deliverables[0]['file'] == 'scripts/sample.py'
        assert deliverables[1]['file'] == 'docs/README.md'

    def test_parse_spec_with_no_deliverables(self, temp_project):
        """Test parsing spec with no deliverables section."""
        spec_content = """
# Task Without Deliverables

Just a description.
"""
        spec_path = temp_project / "empty_spec.md"
        spec_path.write_text(spec_content)

        deliverables = parse_task_spec_for_deliverables(spec_path)

        assert len(deliverables) == 0


class TestQualityGateIntegration:
    """Tests for quality gate verification integration."""

    @patch('verified_todo_update.subprocess.run')
    def test_quality_gate_pass(self, mock_run, sample_task_spec, temp_project):
        """Test successful quality gate verification."""
        # Mock quality gate success
        mock_run.return_value = MagicMock(returncode=0, stdout="PASSED", stderr="")

        passed, report_path = run_quality_gate_verification(
            sample_task_spec,
            temp_project,
            agent_id="test123"
        )

        assert passed is True
        assert report_path is not None
        mock_run.assert_called_once()

    @patch('verified_todo_update.subprocess.run')
    def test_quality_gate_fail(self, mock_run, sample_task_spec, temp_project):
        """Test failed quality gate verification."""
        # Mock quality gate failure
        mock_run.return_value = MagicMock(returncode=1, stdout="FAILED", stderr="")

        passed, report_path = run_quality_gate_verification(
            sample_task_spec,
            temp_project,
            agent_id="test123"
        )

        assert passed is False
        assert report_path is not None

    @patch('verified_todo_update.subprocess.run')
    def test_quality_gate_error(self, mock_run, sample_task_spec, temp_project):
        """Test quality gate error."""
        # Mock quality gate error
        mock_run.return_value = MagicMock(returncode=2, stdout="", stderr="Error")

        passed, report_path = run_quality_gate_verification(
            sample_task_spec,
            temp_project,
            agent_id="test123"
        )

        assert passed is False

    @patch('verified_todo_update.subprocess.run')
    def test_quality_gate_skip(self, mock_run, sample_task_spec, temp_project):
        """Test skipping quality gate."""
        passed, report_path = run_quality_gate_verification(
            sample_task_spec,
            temp_project,
            skip_quality_gate=True
        )

        assert passed is True
        mock_run.assert_not_called()


class TestTodoWriteUpdate:
    """Tests for TodoWrite update logic."""

    def test_update_when_verified(self):
        """Test TodoWrite update when verification passes."""
        result = update_todo_if_verified(
            task_id="test-task",
            status="completed",
            verification_passed=True,
            details={'verified': True}
        )

        # In current implementation, this is a placeholder
        # In production, this would call actual TodoWrite
        assert result is True

    def test_block_when_not_verified(self):
        """Test TodoWrite blocked when verification fails."""
        result = update_todo_if_verified(
            task_id="test-task",
            status="completed",
            verification_passed=False,
            details={'verified': False, 'missing_files': ['file.py']}
        )

        assert result is False


class TestMainWorkflow:
    """Integration tests for main workflow."""

    @patch('verified_todo_update.run_quality_gate_verification')
    @patch('verified_todo_update.verify_deliverables_exist')
    @patch('verified_todo_update.parse_task_spec_for_deliverables')
    def test_main_workflow_success(self, mock_parse, mock_verify, mock_gate,
                                   sample_task_spec, temp_project):
        """Test successful main workflow."""
        # Mock successful verification
        mock_parse.return_value = [{'file': 'test.py'}]
        mock_verify.return_value = (True, [])
        mock_gate.return_value = (True, "report.txt")

        # Would test CLI interface here
        # Currently tested via bash script integration

    @patch('verified_todo_update.verify_deliverables_exist')
    @patch('verified_todo_update.parse_task_spec_for_deliverables')
    def test_main_workflow_missing_files(self, mock_parse, mock_verify,
                                         sample_task_spec, temp_project):
        """Test workflow with missing files."""
        mock_parse.return_value = [{'file': 'missing.py'}]
        mock_verify.return_value = (False, ['missing.py'])

        # Should fail before quality gate
        # Exit code 1 expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
