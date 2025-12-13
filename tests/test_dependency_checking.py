"""
Tests for task dependency checking.

Tests validation of task dependencies before execution.
"""

import os
import pytest
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from check_task_dependencies import (
    parse_task_spec_dependencies,
    check_file_dependencies,
    check_task_dependencies,
    check_env_dependencies,
    Dependencies,
    DependencyCheckResult
)


@pytest.fixture
def temp_project():
    """Create temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)

        # Create sample files
        (project_root / "scripts").mkdir()
        (project_root / "scripts" / "existing.py").write_text("# Exists")

        (project_root / "plans").mkdir()

        yield project_root


@pytest.fixture
def sample_task_spec(temp_project):
    """Create sample task spec with dependencies."""
    spec_content = """
# Sample Task

## Dependencies

- File: scripts/existing.py
- File: scripts/missing.py
- Task: TASK-01
- Task: TASK-02
- Environment: DATABASE_URL
- Environment: API_KEY
"""
    spec_path = temp_project / "task_spec.md"
    spec_path.write_text(spec_content)
    return spec_path


class TestDependencyParsing:
    """Tests for dependency parsing from task specs."""

    def test_parse_file_dependencies(self, sample_task_spec):
        """Test parsing file dependencies."""
        deps = parse_task_spec_dependencies(sample_task_spec)

        assert len(deps.files) == 2
        assert 'scripts/existing.py' in deps.files
        assert 'scripts/missing.py' in deps.files

    def test_parse_task_dependencies(self, sample_task_spec):
        """Test parsing task dependencies."""
        deps = parse_task_spec_dependencies(sample_task_spec)

        assert len(deps.tasks) == 2
        assert 'TASK-01' in deps.tasks
        assert 'TASK-02' in deps.tasks

    def test_parse_env_dependencies(self, sample_task_spec):
        """Test parsing environment variable dependencies."""
        deps = parse_task_spec_dependencies(sample_task_spec)

        assert len(deps.env_vars) == 2
        assert 'DATABASE_URL' in deps.env_vars
        assert 'API_KEY' in deps.env_vars

    def test_parse_no_dependencies(self, temp_project):
        """Test parsing spec with no dependencies."""
        spec_content = """
# Task Without Dependencies

Just a description.
"""
        spec_path = temp_project / "no_deps.md"
        spec_path.write_text(spec_content)

        deps = parse_task_spec_dependencies(spec_path)

        assert len(deps.files) == 0
        assert len(deps.tasks) == 0
        assert len(deps.env_vars) == 0


class TestFileDependencyChecking:
    """Tests for file dependency checking."""

    def test_existing_file_passes(self, temp_project):
        """Test that existing files pass check."""
        files = ['scripts/existing.py']
        results = check_file_dependencies(files, temp_project)

        assert len(results) == 1
        assert results[0].satisfied is True
        assert 'existing.py' in results[0].name

    def test_missing_file_fails(self, temp_project):
        """Test that missing files fail check."""
        files = ['scripts/missing.py']
        results = check_file_dependencies(files, temp_project)

        assert len(results) == 1
        assert results[0].satisfied is False
        assert 'MISSING' in results[0].details

    def test_multiple_files_mixed(self, temp_project):
        """Test checking multiple files with mixed results."""
        files = ['scripts/existing.py', 'scripts/missing.py']
        results = check_file_dependencies(files, temp_project)

        assert len(results) == 2
        satisfied = [r for r in results if r.satisfied]
        unsatisfied = [r for r in results if not r.satisfied]

        assert len(satisfied) == 1
        assert len(unsatisfied) == 1


class TestTaskDependencyChecking:
    """Tests for task dependency checking."""

    def test_completed_task_passes(self, temp_project):
        """Test that completed tasks pass check."""
        # Create plan file with completed task
        plan_dir = temp_project / "plans"
        plan_dir.mkdir(exist_ok=True)

        plan_content = """
## [TASK-01] Example Task

**Status**: Done ✅
"""
        (plan_dir / "plan.md").write_text(plan_content)

        tasks = ['TASK-01']
        results = check_task_dependencies(tasks, temp_project)

        assert len(results) == 1
        assert results[0].satisfied is True

    def test_incomplete_task_fails(self, temp_project):
        """Test that incomplete tasks fail check."""
        tasks = ['TASK-MISSING']
        results = check_task_dependencies(tasks, temp_project)

        assert len(results) == 1
        assert results[0].satisfied is False


class TestEnvDependencyChecking:
    """Tests for environment variable checking."""

    def test_set_env_var_passes(self):
        """Test that set env vars pass check."""
        os.environ['TEST_VAR'] = 'value'

        try:
            env_vars = ['TEST_VAR']
            results = check_env_dependencies(env_vars)

            assert len(results) == 1
            assert results[0].satisfied is True
        finally:
            del os.environ['TEST_VAR']

    def test_unset_env_var_fails(self):
        """Test that unset env vars fail check."""
        # Ensure var is not set
        if 'UNSET_TEST_VAR' in os.environ:
            del os.environ['UNSET_TEST_VAR']

        env_vars = ['UNSET_TEST_VAR']
        results = check_env_dependencies(env_vars)

        assert len(results) == 1
        assert results[0].satisfied is False
        assert 'NOT SET' in results[0].details


class TestDependencyIntegration:
    """Integration tests for full dependency checking."""

    def test_all_deps_satisfied(self, temp_project):
        """Test when all dependencies are satisfied."""
        # Setup: Create all required files
        (temp_project / "scripts" / "file1.py").write_text("# File 1")

        # Setup: Create plan with completed task
        plan_dir = temp_project / "plans"
        plan_dir.mkdir(exist_ok=True)
        (plan_dir / "plan.md").write_text("## [TASK-01]\n\n**Status**: Done ✅")

        # Setup: Set env var
        os.environ['TEST_ENV'] = 'value'

        try:
            deps = Dependencies(
                files=['scripts/file1.py'],
                tasks=['TASK-01'],
                env_vars=['TEST_ENV']
            )

            file_results = check_file_dependencies(deps.files, temp_project)
            task_results = check_task_dependencies(deps.tasks, temp_project)
            env_results = check_env_dependencies(deps.env_vars)

            all_results = file_results + task_results + env_results
            assert all(r.satisfied for r in all_results)
        finally:
            if 'TEST_ENV' in os.environ:
                del os.environ['TEST_ENV']

    def test_some_deps_unsatisfied(self, temp_project):
        """Test when some dependencies are not satisfied."""
        deps = Dependencies(
            files=['scripts/missing.py'],
            tasks=['TASK-MISSING'],
            env_vars=['MISSING_VAR']
        )

        file_results = check_file_dependencies(deps.files, temp_project)
        task_results = check_task_dependencies(deps.tasks, temp_project)
        env_results = check_env_dependencies(deps.env_vars)

        all_results = file_results + task_results + env_results
        assert all(not r.satisfied for r in all_results)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
