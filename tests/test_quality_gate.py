"""
Tests for quality gate functionality.

Tests validation of agent deliverables against task specifications.
"""

import json
import pytest
import tempfile
import yaml
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from quality_gate import (
    parse_task_spec,
    check_file_exists,
    check_line_count,
    load_config,
    generate_report,
    run_quality_gate,
    TaskSpec,
    CheckResult
)


@pytest.fixture
def temp_project():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)

        # Create sample deliverable files
        (project_root / "scripts").mkdir()
        (project_root / "scripts" / "sample.py").write_text("# Sample script\n" * 100)

        (project_root / "docs").mkdir()
        (project_root / "docs" / "README.md").write_text("# Documentation\n" * 50)

        # Create config directory
        (project_root / "config").mkdir()

        yield project_root


@pytest.fixture
def sample_task_spec(temp_project):
    """Create a sample task specification."""
    spec_content = """
# Sample Task

**Deliverables**:
1. **scripts/sample.py** (80-120 lines)
   - Main script implementation
2. **docs/README.md** (40-60 lines)
   - Documentation

**Acceptance checks**:
```bash
[ -f scripts/sample.py ]
[ $(wc -l < scripts/sample.py) -ge 80 ]
python scripts/sample.py --help
```
"""
    spec_path = temp_project / "task_spec.md"
    spec_path.write_text(spec_content)
    return spec_path


@pytest.fixture
def sample_config(temp_project):
    """Create a sample config file."""
    config = {
        'severity_levels': ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'],
        'blocking_severities': ['CRITICAL', 'HIGH'],
        'test_timeout_seconds': 300
    }
    config_path = temp_project / "config" / "quality_gate_config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, 'w') as f:
        yaml.dump(config, f)
    return config_path


class TestTaskSpecParsing:
    """Tests for task specification parsing."""

    def test_parse_task_spec_basic(self, sample_task_spec):
        """Test basic task spec parsing."""
        task_spec = parse_task_spec(sample_task_spec)

        assert task_spec.task_id is not None
        assert len(task_spec.deliverables) == 2
        assert len(task_spec.acceptance_checks) > 0

    def test_parse_deliverables(self, sample_task_spec):
        """Test parsing of deliverables section."""
        task_spec = parse_task_spec(sample_task_spec)

        # Check first deliverable
        deliv1 = task_spec.deliverables[0]
        assert deliv1['file'] == 'scripts/sample.py'
        assert deliv1['min_lines'] == 80
        assert deliv1['max_lines'] == 120

        # Check second deliverable
        deliv2 = task_spec.deliverables[1]
        assert deliv2['file'] == 'docs/README.md'
        assert deliv2['min_lines'] == 40
        assert deliv2['max_lines'] == 60

    def test_parse_acceptance_checks(self, sample_task_spec):
        """Test parsing of acceptance checks."""
        task_spec = parse_task_spec(sample_task_spec)

        assert len(task_spec.acceptance_checks) >= 3
        # Should extract bash commands, not comments
        assert any('scripts/sample.py' in check for check in task_spec.acceptance_checks)

    def test_parse_min_lines_dict(self, sample_task_spec):
        """Test min_lines dictionary creation."""
        task_spec = parse_task_spec(sample_task_spec)

        assert 'scripts/sample.py' in task_spec.min_lines
        assert task_spec.min_lines['scripts/sample.py'] == (80, 120)

        assert 'docs/README.md' in task_spec.min_lines
        assert task_spec.min_lines['docs/README.md'] == (40, 60)


class TestFileExistenceCheck:
    """Tests for file existence checking."""

    def test_file_exists_success(self, temp_project):
        """Test successful file existence check."""
        result = check_file_exists("scripts/sample.py", temp_project)

        assert result.passed is True
        assert result.severity == "CRITICAL"
        assert "exists" in result.actual.lower()

    def test_file_exists_failure(self, temp_project):
        """Test failed file existence check."""
        result = check_file_exists("scripts/missing.py", temp_project)

        assert result.passed is False
        assert result.severity == "CRITICAL"
        assert "missing" in result.actual.lower()

    def test_file_exists_nested_path(self, temp_project):
        """Test file existence check with nested paths."""
        # Create nested directory structure
        (temp_project / "src" / "lib").mkdir(parents=True)
        (temp_project / "src" / "lib" / "module.py").write_text("# Module")

        result = check_file_exists("src/lib/module.py", temp_project)

        assert result.passed is True


class TestLineCountCheck:
    """Tests for line count validation."""

    def test_line_count_within_range(self, temp_project):
        """Test line count check when file is within range."""
        result = check_line_count("scripts/sample.py", 80, 120, temp_project)

        assert result.passed is True
        assert "100 lines" in result.actual

    def test_line_count_too_few(self, temp_project):
        """Test line count check when file has too few lines."""
        result = check_line_count("docs/README.md", 100, 200, temp_project)

        assert result.passed is False
        assert "50 lines" in result.actual
        assert result.severity == "HIGH"

    def test_line_count_too_many(self, temp_project):
        """Test line count check when file has too many lines."""
        result = check_line_count("scripts/sample.py", 10, 50, temp_project)

        assert result.passed is False
        assert "100 lines" in result.actual

    def test_line_count_file_missing(self, temp_project):
        """Test line count check when file is missing."""
        result = check_line_count("missing.py", 50, 100, temp_project)

        assert result.passed is False
        assert "missing" in result.actual.lower()
        assert result.severity == "CRITICAL"

    def test_line_count_read_error(self, temp_project):
        """Test line count check handles read errors."""
        # Create a directory with the same name as expected file
        (temp_project / "broken").mkdir()

        result = check_line_count("broken", 50, 100, temp_project)

        assert result.passed is False
        assert "error" in result.actual.lower()


class TestConfigLoading:
    """Tests for configuration loading."""

    def test_load_config_success(self, sample_config):
        """Test successful config loading."""
        config = load_config(sample_config)

        assert 'severity_levels' in config
        assert 'blocking_severities' in config
        assert 'CRITICAL' in config['blocking_severities']

    def test_load_config_missing_file(self, temp_project):
        """Test config loading with missing file returns defaults."""
        config = load_config(temp_project / "nonexistent.yaml")

        # Should return default config
        assert 'severity_levels' in config
        assert 'blocking_severities' in config

    def test_load_config_default_values(self, temp_project):
        """Test default config values."""
        config = load_config(temp_project / "missing.yaml")

        assert config['severity_levels'] == ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
        assert 'CRITICAL' in config['blocking_severities']
        assert config['test_timeout_seconds'] == 300


class TestReportGeneration:
    """Tests for report generation."""

    def test_generate_report_all_passed(self, sample_task_spec):
        """Test report generation when all checks passed."""
        task_spec = parse_task_spec(sample_task_spec)
        results = [
            CheckResult("check1", True, "Expected", "Actual", "CRITICAL"),
            CheckResult("check2", True, "Expected", "Actual", "HIGH")
        ]
        config = {'blocking_severities': ['CRITICAL', 'HIGH']}

        report, all_passed = generate_report(task_spec, results, config)

        assert all_passed is True
        assert "PASSED" in report
        assert "✓" in report

    def test_generate_report_with_failures(self, sample_task_spec):
        """Test report generation with failures."""
        task_spec = parse_task_spec(sample_task_spec)
        results = [
            CheckResult("check1", True, "Expected", "Actual", "CRITICAL"),
            CheckResult("check2", False, "Expected", "Different", "CRITICAL")
        ]
        config = {'blocking_severities': ['CRITICAL', 'HIGH']}

        report, all_passed = generate_report(task_spec, results, config)

        assert all_passed is False
        assert "FAILED" in report
        assert "✗" in report
        assert "check2" in report

    def test_generate_report_non_blocking_failures(self, sample_task_spec):
        """Test report generation with non-blocking failures."""
        task_spec = parse_task_spec(sample_task_spec)
        results = [
            CheckResult("check1", True, "Expected", "Actual", "CRITICAL"),
            CheckResult("check2", False, "Expected", "Different", "LOW")
        ]
        config = {'blocking_severities': ['CRITICAL', 'HIGH']}

        report, all_passed = generate_report(task_spec, results, config)

        # Should pass because LOW severity failures are not blocking
        assert all_passed is True
        assert "WARNING" in report or "!" in report


class TestQualityGateIntegration:
    """Integration tests for quality gate."""

    def test_run_quality_gate_success(self, sample_task_spec, temp_project):
        """Test full quality gate run with passing deliverables."""
        results, all_passed = run_quality_gate(
            sample_task_spec,
            project_root=temp_project
        )

        assert all_passed is True
        assert len(results) > 0

    def test_run_quality_gate_missing_file(self, temp_project):
        """Test quality gate with missing deliverable."""
        # Create spec with missing file
        spec_content = """
# Task

**Deliverables**:
1. **missing.py** (50-100 lines)
"""
        spec_path = temp_project / "spec.md"
        spec_path.write_text(spec_content)

        results, all_passed = run_quality_gate(
            spec_path,
            project_root=temp_project
        )

        assert all_passed is False
        # Should have failures for missing file
        failures = [r for r in results if not r.passed]
        assert len(failures) > 0

    def test_run_quality_gate_line_count_mismatch(self, temp_project):
        """Test quality gate with line count mismatch."""
        # Create file with wrong line count
        (temp_project / "short.py").write_text("# Short\n" * 10)

        spec_content = """
# Task

**Deliverables**:
1. **short.py** (100-200 lines)
"""
        spec_path = temp_project / "spec.md"
        spec_path.write_text(spec_content)

        results, all_passed = run_quality_gate(
            spec_path,
            project_root=temp_project
        )

        assert all_passed is False
        # Should have line count failure
        line_count_failures = [
            r for r in results
            if not r.passed and "line_count" in r.check_name
        ]
        assert len(line_count_failures) > 0


class TestQualityGateOnHistoricalAgents:
    """Tests for quality gate on historical Day 5 agents."""

    def test_day5_agent_ef82d1bf_should_fail(self, temp_project):
        """Test that Day 5 agent ef82d1bf fails quality gate (incomplete docs)."""
        # Simulate Day 5 task 3 spec and incomplete deliverables
        spec_content = """
# Day 5 Task 3: Update Documentation

**Deliverables**:
1. **docs/QUICK_START.md** (220-250 lines)
2. **docs/TROUBLESHOOTING.md** (300-350 lines)
3. **docs/FAQ.md** (400-450 lines)
"""
        spec_path = temp_project / "day5_task3.md"
        spec_path.write_text(spec_content)

        # Create incomplete docs (like agent ef82d1bf produced)
        (temp_project / "docs").mkdir(exist_ok=True)
        (temp_project / "docs" / "QUICK_START.md").write_text("# Short\n" * 89)
        (temp_project / "docs" / "TROUBLESHOOTING.md").write_text("# Short\n" * 81)
        # FAQ.md is missing

        results, all_passed = run_quality_gate(
            spec_path,
            agent_id="ef82d1bf",
            project_root=temp_project
        )

        # Gate should FAIL
        assert all_passed is False

        # Should have multiple failures
        failures = [r for r in results if not r.passed]
        assert len(failures) >= 3  # FAQ missing, QUICK_START too short, TROUBLESHOOTING too short

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
