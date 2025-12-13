"""
Tests for automatic agent output extraction (DC-05).

Tests the wrapper that adds task spec validation to the PH-03 implementation.
"""

import pytest
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from auto_extract_agent_outputs import (
    load_task_spec_deliverables,
    validate_extracted_files,
    ExtractionResult
)


@pytest.fixture
def sample_task_spec(tmp_path):
    """Create sample task specification."""
    spec_content = """
# Sample Task

## Description
Test task for extraction.

**Deliverables**:
1. **docs/QUICK_START.md** (220-250 lines)
   - Quick start guide
2. **docs/TROUBLESHOOTING.md** (300-350 lines)
   - Troubleshooting guide
3. **scripts/example.py** (100-150 lines)
   - Example script

## Additional Notes
Testing task spec parsing.
"""
    spec_path = tmp_path / "task_spec.md"
    spec_path.write_text(spec_content)
    return spec_path


@pytest.fixture
def sample_task_spec_no_deliverables(tmp_path):
    """Create task spec with no deliverables section."""
    spec_content = """
# Task Without Deliverables

Just a description with no deliverables.
"""
    spec_path = tmp_path / "no_deliv_spec.md"
    spec_path.write_text(spec_content)
    return spec_path


class TestTaskSpecParsing:
    """Tests for task spec deliverable parsing."""

    def test_parse_deliverables(self, sample_task_spec):
        """Test parsing deliverables from task spec."""
        deliverables = load_task_spec_deliverables(sample_task_spec)

        assert len(deliverables) == 3
        assert 'docs/QUICK_START.md' in deliverables
        assert 'docs/TROUBLESHOOTING.md' in deliverables
        assert 'scripts/example.py' in deliverables

    def test_parse_no_deliverables(self, sample_task_spec_no_deliverables):
        """Test parsing spec with no deliverables."""
        deliverables = load_task_spec_deliverables(sample_task_spec_no_deliverables)

        assert len(deliverables) == 0

    def test_parse_missing_file(self, tmp_path):
        """Test handling of missing task spec file."""
        missing_spec = tmp_path / "missing.md"
        deliverables = load_task_spec_deliverables(missing_spec)

        assert len(deliverables) == 0


class TestExtractionValidation:
    """Tests for extraction result validation against task spec."""

    def test_all_deliverables_extracted(self):
        """Test validation when all deliverables extracted."""
        results = [
            ExtractionResult('docs/QUICK_START.md', True, 230, None),
            ExtractionResult('docs/TROUBLESHOOTING.md', True, 320, None),
            ExtractionResult('scripts/example.py', True, 120, None)
        ]
        expected = ['docs/QUICK_START.md', 'docs/TROUBLESHOOTING.md', 'scripts/example.py']

        all_found, missing = validate_extracted_files(results, expected)

        assert all_found is True
        assert len(missing) == 0

    def test_some_deliverables_missing(self):
        """Test validation when some deliverables not extracted."""
        results = [
            ExtractionResult('docs/QUICK_START.md', True, 230, None)
        ]
        expected = ['docs/QUICK_START.md', 'docs/TROUBLESHOOTING.md', 'scripts/example.py']

        all_found, missing = validate_extracted_files(results, expected)

        assert all_found is False
        assert len(missing) == 2
        assert 'docs/TROUBLESHOOTING.md' in missing
        assert 'scripts/example.py' in missing

    def test_extra_files_extracted(self):
        """Test validation when extra files extracted (not in spec)."""
        results = [
            ExtractionResult('docs/QUICK_START.md', True, 230, None),
            ExtractionResult('docs/EXTRA.md', True, 100, None)  # Not in spec
        ]
        expected = ['docs/QUICK_START.md']

        all_found, missing = validate_extracted_files(results, expected)

        # Extra files OK, as long as expected ones present
        assert all_found is True
        assert len(missing) == 0

    def test_failed_extractions_not_counted(self):
        """Test that failed extractions don't count as extracted."""
        results = [
            ExtractionResult('docs/QUICK_START.md', True, 230, None),
            ExtractionResult('docs/TROUBLESHOOTING.md', False, 0, "Validation failed")
        ]
        expected = ['docs/QUICK_START.md', 'docs/TROUBLESHOOTING.md']

        all_found, missing = validate_extracted_files(results, expected)

        assert all_found is False
        assert 'docs/TROUBLESHOOTING.md' in missing

    def test_empty_expectations(self):
        """Test validation with no expected deliverables."""
        results = [
            ExtractionResult('some/file.py', True, 100, None)
        ]
        expected = []

        all_found, missing = validate_extracted_files(results, expected)

        # If no expectations, consider it successful
        assert all_found is True
        assert len(missing) == 0


class TestIntegration:
    """Integration tests for the full workflow."""

    def test_task_spec_driven_extraction(self, sample_task_spec, tmp_path):
        """Test extraction workflow driven by task spec."""
        # Parse deliverables
        deliverables = load_task_spec_deliverables(sample_task_spec)
        assert len(deliverables) == 3

        # Simulate extraction results
        results = [
            ExtractionResult(d, True, 200, None) for d in deliverables
        ]

        # Validate
        all_found, missing = validate_extracted_files(results, deliverables)
        assert all_found is True
        assert len(missing) == 0

    def test_partial_extraction_from_agent(self, sample_task_spec):
        """Test handling of partial extraction (some files missing)."""
        deliverables = load_task_spec_deliverables(sample_task_spec)

        # Simulate only 2 of 3 files extracted
        results = [
            ExtractionResult('docs/QUICK_START.md', True, 230, None),
            ExtractionResult('docs/TROUBLESHOOTING.md', True, 320, None)
            # scripts/example.py missing
        ]

        all_found, missing = validate_extracted_files(results, deliverables)

        assert all_found is False
        assert 'scripts/example.py' in missing
        assert len(missing) == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
