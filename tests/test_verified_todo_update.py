"""
Tests for verified TodoWrite update functionality.

Tests the wrapper that verifies deliverables before allowing TodoWrite completion.
"""

import json
import pytest
import tempfile
import yaml
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from verified_todo_update import (
    verify_deliverables_exist,
    run_quality_gate_verification,
    update_todo_if_verified,
    load_task_spec,
    main
)
from quality_gate import parse_task_spec


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
        task_spec = parse_task_spec(sample_task_spec)
        deliverables = task_spec.deliverables

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

        task_spec = parse_task_spec(spec_path)
        deliverables = task_spec.deliverables

        assert len(deliverables) == 0


class TestQualityGateIntegration:
    """Tests for quality gate verification integration."""

    def test_quality_gate_pass(self, sample_task_spec, temp_project):
        """Test successful quality gate verification."""
        # Real quality gate with valid deliverables should pass
        passed, summary = run_quality_gate_verification(
            sample_task_spec,
            temp_project,
            agent_id="test123"
        )

        assert passed is True
        assert "Quality Gate" in summary
        assert "passed" in summary

    def test_quality_gate_fail(self, temp_project):
        """Test failed quality gate verification."""
        # Create spec with missing deliverables
        spec_content = """
# Failed Task

**Deliverables**:
1. **missing.py** (100-200 lines)
"""
        spec_path = temp_project / "fail_spec.md"
        spec_path.write_text(spec_content)

        passed, summary = run_quality_gate_verification(
            spec_path,
            temp_project,
            agent_id="test123"
        )

        assert passed is False
        assert "Quality Gate" in summary or "failures" in summary.lower()

    def test_quality_gate_with_line_count_mismatch(self, temp_project):
        """Test quality gate with line count mismatch."""
        # Create file with wrong line count
        (temp_project / "short.py").write_text("# Short\n" * 10)

        spec_content = """
# Task with Wrong Line Count

**Deliverables**:
1. **short.py** (100-200 lines)
"""
        spec_path = temp_project / "spec.md"
        spec_path.write_text(spec_content)

        passed, summary = run_quality_gate_verification(
            spec_path,
            temp_project,
            agent_id="test123"
        )

        assert passed is False
        assert "failure" in summary.lower() or "failed" in summary.lower()


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

    def test_main_workflow_success(self, sample_task_spec, temp_project):
        """Test successful main workflow."""
        # Load real task spec
        task_spec = load_task_spec(sample_task_spec)

        assert task_spec is not None
        assert 'deliverables' in task_spec
        assert len(task_spec['deliverables']) == 2

        # Verify real deliverables
        all_exist, missing = verify_deliverables_exist(
            task_spec['deliverables'],
            temp_project
        )

        assert all_exist is True
        assert len(missing) == 0

        # Run real quality gate
        passed, summary = run_quality_gate_verification(
            sample_task_spec,
            temp_project,
            agent_id="test123"
        )

        assert passed is True

    def test_main_workflow_missing_files(self, temp_project):
        """Test workflow with missing files."""
        # Create spec with missing deliverables
        spec_content = """
# Task with Missing Files

**Deliverables**:
1. **missing.py** (50-100 lines)
"""
        spec_path = temp_project / "spec.md"
        spec_path.write_text(spec_content)

        # Load real task spec
        task_spec = load_task_spec(spec_path)

        # Verify deliverables - should fail
        all_exist, missing = verify_deliverables_exist(
            task_spec['deliverables'],
            temp_project
        )

        assert all_exist is False
        assert 'missing.py' in missing


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
