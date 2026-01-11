"""
Tests for analysis verification framework.

Tests systematic verification of claims in analysis documents.
"""

import json
import pytest
import tempfile
import yaml
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from verify_analysis import (
    load_verification_config,
    extract_claims_from_document,
    verify_file_exists_claim,
    verify_file_missing_claim,
    verify_line_count_claim,
    verify_claims,
    generate_verification_report,
    run_verification,
    Claim,
    VerificationResult
)


@pytest.fixture
def temp_project():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)

        # Create sample files for verification
        (project_root / "src").mkdir()
        (project_root / "src" / "main.py").write_text("# Main\n" * 100)

        (project_root / "docs").mkdir()
        (project_root / "docs" / "README.md").write_text("# Documentation\n" * 50)

        # Create config directory
        (project_root / "config").mkdir()

        yield project_root


@pytest.fixture
def sample_analysis_doc(temp_project):
    """Create a sample analysis document with claims."""
    content = """
# Analysis Report

## File Status

File `src/main.py` exists and contains 100 lines of code.

File `docs/README.md` is present with 50 lines of documentation.

File `docs/FAQ.md` is missing and needs to be created.

## Test Results

Tests in `tests/test_main.py` passed successfully.

## Agent Output

Agent ef82d1bf produced the documentation files.
"""
    doc_path = temp_project / "analysis.md"
    doc_path.write_text(content)
    return doc_path


@pytest.fixture
def sample_config(temp_project):
    """Create a sample verification config."""
    config = {
        'claim_patterns': {
            'file_exists': [
                r'(?:File|Document)\s+`([^`]+)`\s+(?:exists|present)',
                r'`([^`]+)`\s+is present'
            ],
            'line_count': [
                r'`([^`]+)`.*?(\d+)\s+lines'
            ],
            'missing_file': [
                r'`([^`]+)`.*?(?:missing|is missing)'
            ]
        },
        'require_evidence': True,
        'min_verification_rate': 0.8
    }
    config_path = temp_project / "config" / "verification_checklist.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, 'w') as f:
        yaml.dump(config, f)
    return config_path


class TestConfigLoading:
    """Tests for configuration loading."""

    def test_load_config_success(self, sample_config):
        """Test successful config loading."""
        config = load_verification_config(sample_config)

        assert 'claim_patterns' in config
        assert 'file_exists' in config['claim_patterns']
        assert config['min_verification_rate'] == 0.8

    def test_load_config_missing_file(self, temp_project):
        """Test config loading with missing file returns defaults."""
        config = load_verification_config(temp_project / "nonexistent.yaml")

        # Should return default config
        assert 'claim_patterns' in config
        assert 'min_verification_rate' in config

    def test_load_config_default_values(self, temp_project):
        """Test default config values."""
        config = load_verification_config(temp_project / "missing.yaml")

        assert config['require_evidence'] is True
        assert config['min_verification_rate'] == 0.8


class TestClaimExtraction:
    """Tests for claim extraction from documents."""

    def test_extract_file_exists_claims(self, sample_analysis_doc, sample_config):
        """Test extraction of file existence claims."""
        config = load_verification_config(sample_config)
        claims = extract_claims_from_document(sample_analysis_doc, config)

        file_exists_claims = [c for c in claims if c.claim_type == "file_exists"]
        assert len(file_exists_claims) >= 2

        # Check specific claims
        subjects = [c.subject for c in file_exists_claims]
        assert "src/main.py" in subjects
        assert "docs/README.md" in subjects

    def test_extract_line_count_claims(self, sample_analysis_doc, sample_config):
        """Test extraction of line count claims."""
        config = load_verification_config(sample_config)
        claims = extract_claims_from_document(sample_analysis_doc, config)

        line_count_claims = [c for c in claims if c.claim_type == "line_count"]
        assert len(line_count_claims) >= 2

        # Check specific claims
        for claim in line_count_claims:
            if claim.subject == "src/main.py":
                assert "100" in claim.expected
            elif claim.subject == "docs/README.md":
                assert "50" in claim.expected

    def test_extract_missing_file_claims(self, sample_analysis_doc, sample_config):
        """Test extraction of missing file claims."""
        config = load_verification_config(sample_config)
        claims = extract_claims_from_document(sample_analysis_doc, config)

        missing_claims = [c for c in claims if c.claim_type == "file_missing"]
        assert len(missing_claims) >= 1

        # Check specific claim
        assert any("FAQ.md" in c.subject for c in missing_claims)

    def test_extract_claims_with_location(self, sample_analysis_doc, sample_config):
        """Test that extracted claims include location information."""
        config = load_verification_config(sample_config)
        claims = extract_claims_from_document(sample_analysis_doc, config)

        for claim in claims:
            assert claim.location is not None
            assert "line" in claim.location

    def test_extract_no_duplicate_claims(self, sample_analysis_doc, sample_config):
        """Test that same claim isn't extracted multiple times."""
        config = load_verification_config(sample_config)
        claims = extract_claims_from_document(sample_analysis_doc, config)

        # Check for exact duplicates
        claim_signatures = []
        for claim in claims:
            signature = (claim.claim_type, claim.subject, claim.expected)
            assert signature not in claim_signatures
            claim_signatures.append(signature)


class TestFileExistsVerification:
    """Tests for file existence claim verification."""

    def test_verify_file_exists_success(self, temp_project):
        """Test successful file existence verification."""
        claim = Claim(
            claim_type="file_exists",
            location="line 5",
            subject="src/main.py",
            expected="File exists"
        )

        verified_claim = verify_file_exists_claim(claim, temp_project)

        assert verified_claim.verified is True
        assert "exists" in verified_claim.actual.lower()
        assert verified_claim.evidence is not None

    def test_verify_file_exists_failure(self, temp_project):
        """Test failed file existence verification."""
        claim = Claim(
            claim_type="file_exists",
            location="line 5",
            subject="nonexistent.py",
            expected="File exists"
        )

        verified_claim = verify_file_exists_claim(claim, temp_project)

        assert verified_claim.verified is False
        assert "not found" in verified_claim.actual.lower()
        assert verified_claim.evidence is not None


class TestFileMissingVerification:
    """Tests for file missing claim verification."""

    def test_verify_file_missing_success(self, temp_project):
        """Test successful verification of missing file claim."""
        claim = Claim(
            claim_type="file_missing",
            location="line 10",
            subject="docs/FAQ.md",
            expected="File missing"
        )

        verified_claim = verify_file_missing_claim(claim, temp_project)

        assert verified_claim.verified is True
        assert "missing" in verified_claim.actual.lower()

    def test_verify_file_missing_failure(self, temp_project):
        """Test failed verification when file actually exists."""
        claim = Claim(
            claim_type="file_missing",
            location="line 10",
            subject="src/main.py",  # This file exists
            expected="File missing"
        )

        verified_claim = verify_file_missing_claim(claim, temp_project)

        assert verified_claim.verified is False
        assert "exists" in verified_claim.actual.lower()


class TestLineCountVerification:
    """Tests for line count claim verification."""

    def test_verify_line_count_exact_match(self, temp_project):
        """Test line count verification with exact match."""
        claim = Claim(
            claim_type="line_count",
            location="line 7",
            subject="src/main.py",
            expected="100 lines"
        )

        verified_claim = verify_line_count_claim(claim, temp_project)

        assert verified_claim.verified is True
        assert "100" in verified_claim.actual

    def test_verify_line_count_within_tolerance(self, temp_project):
        """Test line count verification within tolerance range."""
        claim = Claim(
            claim_type="line_count",
            location="line 7",
            subject="src/main.py",
            expected="98 lines"  # Within 5% of 100
        )

        verified_claim = verify_line_count_claim(claim, temp_project)

        assert verified_claim.verified is True

    def test_verify_line_count_mismatch(self, temp_project):
        """Test line count verification with mismatch."""
        claim = Claim(
            claim_type="line_count",
            location="line 7",
            subject="src/main.py",
            expected="200 lines"  # Actual is 100
        )

        verified_claim = verify_line_count_claim(claim, temp_project)

        assert verified_claim.verified is False
        assert "does NOT match" in verified_claim.actual

    def test_verify_line_count_file_missing(self, temp_project):
        """Test line count verification when file is missing."""
        claim = Claim(
            claim_type="line_count",
            location="line 7",
            subject="missing.py",
            expected="50 lines"
        )

        verified_claim = verify_line_count_claim(claim, temp_project)

        assert verified_claim.verified is False
        assert "missing" in verified_claim.actual.lower()


class TestClaimVerification:
    """Tests for full claim verification."""

    def test_verify_claims_mixed_results(self, temp_project, sample_config):
        """Test verification of mixed claims."""
        claims = [
            Claim("file_exists", "line 1", "src/main.py", "File exists"),
            Claim("file_exists", "line 2", "missing.py", "File exists"),
            Claim("line_count", "line 3", "src/main.py", "100 lines")
        ]

        config = load_verification_config(sample_config)
        verified_claims = verify_claims(claims, temp_project, config)

        assert len(verified_claims) == 3

        # First claim should pass
        assert verified_claims[0].verified is True

        # Second claim should fail
        assert verified_claims[1].verified is False

        # Third claim should pass
        assert verified_claims[2].verified is True


class TestReportGeneration:
    """Tests for verification report generation."""

    def test_generate_text_report(self):
        """Test text format report generation."""
        result = VerificationResult(
            document_path="analysis.md",
            total_claims=5,
            verified_claims=4,
            unverified_claims=1,
            failed_claims=1,
            claims=[
                Claim("file_exists", "line 1", "file.py", "exists", "exists", True, "fs_check", "Verified"),
                Claim("file_exists", "line 2", "missing.py", "exists", "not found", False, "fs_check", "Failed")
            ],
            verification_passed=False
        )

        report = generate_verification_report(result, "text")

        assert "ANALYSIS VERIFICATION REPORT" in report
        assert "analysis.md" in report
        assert "Total claims found: 5" in report
        assert "Verified claims:    4" in report
        assert "VERIFICATION FAILED" in report

    def test_generate_json_report(self):
        """Test JSON format report generation."""
        result = VerificationResult(
            document_path="analysis.md",
            total_claims=2,
            verified_claims=2,
            unverified_claims=0,
            failed_claims=0,
            claims=[
                Claim("file_exists", "line 1", "file.py", "exists", "exists", True, "fs_check", "OK")
            ],
            verification_passed=True
        )

        report = generate_verification_report(result, "json")
        data = json.loads(report)

        assert data['document_path'] == "analysis.md"
        assert data['total_claims'] == 2
        assert data['verification_passed'] is True
        assert len(data['claims']) == 1

    def test_generate_yaml_report(self):
        """Test YAML format report generation."""
        result = VerificationResult(
            document_path="analysis.md",
            total_claims=1,
            verified_claims=1,
            unverified_claims=0,
            failed_claims=0,
            claims=[],
            verification_passed=True
        )

        report = generate_verification_report(result, "yaml")
        data = yaml.safe_load(report)

        assert data['document_path'] == "analysis.md"
        assert data['verification_passed'] is True


class TestVerificationIntegration:
    """Integration tests for full verification process."""

    def test_run_verification_all_passed(self, sample_analysis_doc, temp_project):
        """Test full verification with all claims verified."""
        result = run_verification(
            sample_analysis_doc,
            temp_project
        )

        assert result.total_claims > 0
        # Some claims should verify (files that exist)
        assert result.verified_claims > 0

    def test_run_verification_with_failures(self, temp_project):
        """Test verification with failed claims."""
        # Create doc with false claims
        doc_content = """
# Analysis

File `nonexistent.py` exists with 100 lines.
File `docs/README.md` has 500 lines.
"""
        doc_path = temp_project / "bad_analysis.md"
        doc_path.write_text(doc_content)

        result = run_verification(doc_path, temp_project)

        # Should have failures
        assert result.failed_claims > 0
        assert result.verification_passed is False

    def test_run_verification_rate_threshold(self, temp_project):
        """Test verification rate threshold enforcement."""
        # Create doc where less than 80% claims verify
        doc_content = """
# Analysis

File `src/main.py` exists.
File `missing1.py` exists.
File `missing2.py` exists.
File `missing3.py` exists.
File `missing4.py` exists.
"""
        doc_path = temp_project / "low_verification.md"
        doc_path.write_text(doc_content)

        result = run_verification(doc_path, temp_project)

        # Verification rate should be below threshold
        verification_rate = result.verified_claims / max(1, result.total_claims)
        assert verification_rate < 0.8
        assert result.verification_passed is False


class TestVerificationOnReadinessAnalysis:
    """Tests for verification on actual readiness analysis."""

    def test_verify_readiness_analysis_structure(self, temp_project):
        """Test verification of readiness analysis document structure."""
        # Create a mock readiness analysis similar to reports/readiness.md
        analysis_content = """
# Production Readiness Analysis

## Executive Summary

Grade: C+ (70/100)

## Task Review

### Task D5-T1: Monitoring Script

File `scripts/monitor_telemetry_health.py` created with 213 lines.

### Task D5-T2: Backup Script

File `scripts/backup_telemetry_db.py` created with 168 lines.

### Task D5-T3: Documentation

File `docs/QUICK_START.md` created with 89 lines (incomplete - expected 230).
File `docs/FAQ.md` is missing completely.

## Gap Analysis

Total missing documentation: 1,071 lines across 4 files.
"""
        doc_path = temp_project / "readiness.md"
        doc_path.write_text(analysis_content)

        # Create some of the mentioned files
        (temp_project / "scripts").mkdir(exist_ok=True)
        (temp_project / "scripts" / "monitor_telemetry_health.py").write_text("# Monitor\n" * 213)
        (temp_project / "scripts" / "backup_telemetry_db.py").write_text("# Backup\n" * 168)

        (temp_project / "docs").mkdir(exist_ok=True)
        (temp_project / "docs" / "QUICK_START.md").write_text("# Quick\n" * 89)
        # FAQ.md intentionally missing

        result = run_verification(doc_path, temp_project)

        # Should extract and verify multiple claims
        assert result.total_claims >= 4

        # Should verify existing files correctly
        monitor_claims = [c for c in result.claims if "monitor_telemetry_health.py" in c.subject]
        assert len(monitor_claims) > 0

        # Should verify missing file claim
        faq_claims = [c for c in result.claims if "FAQ.md" in c.subject and c.claim_type == "file_missing"]
        assert len(faq_claims) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
