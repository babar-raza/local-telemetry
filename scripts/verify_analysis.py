"""
Analysis Verification Framework.

Systematically verifies claims in analysis documents before publication.
Prevents unverified claims from being published as fact.
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml


@dataclass
class Claim:
    """A factual claim made in an analysis document."""
    claim_type: str  # "file_exists", "line_count", "test_result", "agent_output"
    location: str  # Line number or section in document
    subject: str  # What is being claimed about (file path, test name, etc.)
    expected: str  # Expected value or state
    actual: Optional[str] = None  # Actual verified value
    verified: bool = False  # Whether claim has been verified
    verification_method: str = ""  # How verification was performed
    evidence: str = ""  # Evidence for verification result


@dataclass
class VerificationResult:
    """Result of verification process."""
    document_path: str
    total_claims: int
    verified_claims: int
    unverified_claims: int
    failed_claims: int
    claims: List[Claim]
    verification_passed: bool


def load_verification_config(config_path: Path) -> dict:
    """Load verification configuration from YAML."""
    if not config_path.exists():
        # Return default configuration
        return {
            'claim_patterns': {
                'file_exists': [
                    r'(?:File|Document)\s+`([^`]+)`\s+(?:exists|present|found)',
                    r'`([^`]+)`\s+(?:exists|was created|is present)'
                ],
                'line_count': [
                    r'`([^`]+)`.*?(\d+)\s+lines',
                    r'(\d+)\s+lines.*?`([^`]+)`'
                ],
                'missing_file': [
                    r'`([^`]+)`.*?(?:missing|not found|does not exist)',
                    r'(?:missing|not found).*?`([^`]+)`'
                ]
            },
            'require_evidence': True,
            'min_verification_rate': 0.8  # 80% of claims must be verified
        }

    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def extract_claims_from_document(doc_path: Path, config: dict) -> List[Claim]:
    """
    Parse analysis document to extract factual claims.

    Args:
        doc_path: Path to analysis document
        config: Verification configuration

    Returns:
        List of extracted claims
    """
    content = doc_path.read_text(encoding='utf-8')
    lines = content.split('\n')
    claims = []

    claim_patterns = config.get('claim_patterns', {})

    # Extract file existence claims
    for pattern_str in claim_patterns.get('file_exists', []):
        pattern = re.compile(pattern_str, re.IGNORECASE)
        for line_num, line in enumerate(lines, 1):
            for match in pattern.finditer(line):
                filepath = match.group(1)
                claims.append(Claim(
                    claim_type="file_exists",
                    location=f"line {line_num}",
                    subject=filepath,
                    expected="File exists",
                    verification_method="filesystem_check"
                ))

    # Extract line count claims
    for pattern_str in claim_patterns.get('line_count', []):
        pattern = re.compile(pattern_str, re.IGNORECASE)
        for line_num, line in enumerate(lines, 1):
            matches = pattern.finditer(line)
            for match in matches:
                groups = match.groups()
                # Pattern might have (file, count) or (count, file)
                if len(groups) >= 2:
                    # Determine which group is the number
                    if groups[0].isdigit():
                        count, filepath = groups[0], groups[1]
                    else:
                        filepath, count = groups[0], groups[1]

                    claims.append(Claim(
                        claim_type="line_count",
                        location=f"line {line_num}",
                        subject=filepath,
                        expected=f"{count} lines",
                        verification_method="line_count_check"
                    ))

    # Extract missing file claims
    for pattern_str in claim_patterns.get('missing_file', []):
        pattern = re.compile(pattern_str, re.IGNORECASE)
        for line_num, line in enumerate(lines, 1):
            for match in pattern.finditer(line):
                filepath = match.group(1)
                claims.append(Claim(
                    claim_type="file_missing",
                    location=f"line {line_num}",
                    subject=filepath,
                    expected="File missing",
                    verification_method="filesystem_check"
                ))

    return claims


def verify_file_exists_claim(claim: Claim, project_root: Path) -> Claim:
    """Verify a file existence claim."""
    file_path = project_root / claim.subject

    if file_path.exists():
        claim.verified = True
        claim.actual = "File exists"
        claim.evidence = f"Verified at {file_path}"
    else:
        claim.verified = False
        claim.actual = "File NOT FOUND"
        claim.evidence = f"File not found at {file_path}"

    return claim


def verify_file_missing_claim(claim: Claim, project_root: Path) -> Claim:
    """Verify a claim that a file is missing."""
    file_path = project_root / claim.subject

    if not file_path.exists():
        claim.verified = True
        claim.actual = "File missing (as expected)"
        claim.evidence = f"Confirmed missing at {file_path}"
    else:
        claim.verified = False
        claim.actual = "File EXISTS (contradicts claim)"
        claim.evidence = f"File found at {file_path}"

    return claim


def verify_line_count_claim(claim: Claim, project_root: Path) -> Claim:
    """Verify a line count claim."""
    file_path = project_root / claim.subject

    if not file_path.exists():
        claim.verified = False
        claim.actual = "Cannot verify: file not found"
        claim.evidence = f"File not found at {file_path}"
        return claim

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            actual_lines = len(f.readlines())

        # Extract expected count from claim
        expected_match = re.search(r'(\d+)', claim.expected)
        if expected_match:
            expected_count = int(expected_match.group(1))

            # Allow 5% tolerance
            tolerance = max(5, int(expected_count * 0.05))
            lower_bound = expected_count - tolerance
            upper_bound = expected_count + tolerance

            if lower_bound <= actual_lines <= upper_bound:
                claim.verified = True
                claim.actual = f"{actual_lines} lines (matches claim)"
                claim.evidence = f"Line count verified: {actual_lines} lines"
            else:
                claim.verified = False
                claim.actual = f"{actual_lines} lines (does NOT match claim of {expected_count})"
                claim.evidence = f"Line count mismatch: actual {actual_lines}, claimed {expected_count}"
        else:
            claim.verified = False
            claim.actual = f"{actual_lines} lines"
            claim.evidence = "Could not parse expected line count from claim"

    except Exception as e:
        claim.verified = False
        claim.actual = f"Error reading file: {str(e)}"
        claim.evidence = f"Verification error: {str(e)}"

    return claim


def verify_claims(claims: List[Claim], project_root: Path, config: dict) -> List[Claim]:
    """
    Verify all extracted claims.

    Args:
        claims: List of claims to verify
        project_root: Project root directory
        config: Verification configuration

    Returns:
        List of claims with verification results
    """
    verified_claims = []

    for claim in claims:
        if claim.claim_type == "file_exists":
            verified_claims.append(verify_file_exists_claim(claim, project_root))
        elif claim.claim_type == "file_missing":
            verified_claims.append(verify_file_missing_claim(claim, project_root))
        elif claim.claim_type == "line_count":
            verified_claims.append(verify_line_count_claim(claim, project_root))
        else:
            # Unknown claim type, mark as unverified
            claim.verified = False
            claim.actual = "Unknown claim type"
            claim.evidence = f"No verification method for claim type: {claim.claim_type}"
            verified_claims.append(claim)

    return verified_claims


def generate_verification_report(
    result: VerificationResult,
    output_format: str = "text"
) -> str:
    """Generate verification report in specified format."""

    if output_format == "json":
        # Convert to dict for JSON serialization
        result_dict = {
            'document_path': result.document_path,
            'total_claims': result.total_claims,
            'verified_claims': result.verified_claims,
            'unverified_claims': result.unverified_claims,
            'failed_claims': result.failed_claims,
            'verification_passed': result.verification_passed,
            'claims': [
                {
                    'claim_type': c.claim_type,
                    'location': c.location,
                    'subject': c.subject,
                    'expected': c.expected,
                    'actual': c.actual,
                    'verified': c.verified,
                    'verification_method': c.verification_method,
                    'evidence': c.evidence
                }
                for c in result.claims
            ]
        }
        return json.dumps(result_dict, indent=2)

    elif output_format == "yaml":
        result_dict = {
            'document_path': result.document_path,
            'total_claims': result.total_claims,
            'verified_claims': result.verified_claims,
            'unverified_claims': result.unverified_claims,
            'failed_claims': result.failed_claims,
            'verification_passed': result.verification_passed,
            'claims': [asdict(c) for c in result.claims]
        }
        return yaml.dump(result_dict)

    else:  # text format
        lines = []
        lines.append("=" * 70)
        lines.append("ANALYSIS VERIFICATION REPORT")
        lines.append("=" * 70)
        lines.append(f"Document: {result.document_path}")
        lines.append("")

        # Summary
        lines.append("SUMMARY")
        lines.append("-" * 70)
        lines.append(f"Total claims found: {result.total_claims}")
        lines.append(f"Verified claims:    {result.verified_claims} ({result.verified_claims/max(1, result.total_claims)*100:.1f}%)")
        lines.append(f"Unverified claims:  {result.unverified_claims}")
        lines.append(f"Failed claims:      {result.failed_claims}")
        lines.append("")

        if result.verification_passed:
            lines.append("✓ VERIFICATION PASSED")
        else:
            lines.append("✗ VERIFICATION FAILED")
        lines.append("")

        # Unverified/Failed claims
        unverified = [c for c in result.claims if not c.verified]
        if unverified:
            lines.append("UNVERIFIED/FAILED CLAIMS")
            lines.append("-" * 70)
            for claim in unverified:
                lines.append(f"✗ [{claim.claim_type}] {claim.subject}")
                lines.append(f"  Location: {claim.location}")
                lines.append(f"  Expected: {claim.expected}")
                lines.append(f"  Actual:   {claim.actual}")
                lines.append(f"  Evidence: {claim.evidence}")
                lines.append("")

        # Verified claims
        verified = [c for c in result.claims if c.verified]
        if verified:
            lines.append("VERIFIED CLAIMS")
            lines.append("-" * 70)
            for claim in verified:
                lines.append(f"✓ [{claim.claim_type}] {claim.subject}")
                lines.append(f"  Location: {claim.location}")
                lines.append(f"  Evidence: {claim.evidence}")
            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)


def run_verification(
    doc_path: Path,
    project_root: Path,
    config_path: Optional[Path] = None
) -> VerificationResult:
    """
    Run verification on an analysis document.

    Args:
        doc_path: Path to analysis document
        project_root: Project root directory
        config_path: Optional path to verification config

    Returns:
        VerificationResult object
    """
    # Load configuration
    if config_path is None:
        config_path = project_root / "config" / "verification_checklist.yaml"

    config = load_verification_config(config_path)

    # Extract claims from document
    claims = extract_claims_from_document(doc_path, config)

    # Verify claims
    verified_claims = verify_claims(claims, project_root, config)

    # Calculate statistics
    total_claims = len(verified_claims)
    verified_count = sum(1 for c in verified_claims if c.verified)
    failed_count = sum(1 for c in verified_claims if not c.verified and c.actual != "Unknown claim type")
    unverified_count = total_claims - verified_count

    # Determine if verification passed
    min_verification_rate = config.get('min_verification_rate', 0.8)
    verification_rate = verified_count / max(1, total_claims)
    verification_passed = verification_rate >= min_verification_rate and failed_count == 0

    return VerificationResult(
        document_path=str(doc_path),
        total_claims=total_claims,
        verified_claims=verified_count,
        unverified_claims=unverified_count,
        failed_claims=failed_count,
        claims=verified_claims,
        verification_passed=verification_passed
    )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify claims in analysis documents before publication"
    )
    parser.add_argument(
        "document",
        help="Path to analysis document to verify"
    )
    parser.add_argument(
        "--config",
        help="Path to verification config file"
    )
    parser.add_argument(
        "--output",
        help="Output report file path"
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "yaml"],
        default="text",
        help="Output format"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show claims that would be verified without executing verification"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Actually perform verification (default if not dry-run)"
    )

    args = parser.parse_args()

    doc_path = Path(args.document)
    if not doc_path.exists():
        print(f"Error: Document not found: {doc_path}", file=sys.stderr)
        return 2

    project_root = Path.cwd()
    config_path = Path(args.config) if args.config else None

    # Load config
    if config_path is None:
        config_path = project_root / "config" / "verification_checklist.yaml"
    config = load_verification_config(config_path)

    if args.dry_run:
        # Just extract and show claims without verifying
        claims = extract_claims_from_document(doc_path, config)
        print(f"Document: {doc_path}")
        print(f"Claims found: {len(claims)}")
        print("")
        for i, claim in enumerate(claims, 1):
            print(f"{i}. [{claim.claim_type}] {claim.subject}")
            print(f"   Location: {claim.location}")
            print(f"   Expected: {claim.expected}")
            print(f"   Verification method: {claim.verification_method}")
            print("")
        return 0

    # Run verification
    result = run_verification(doc_path, project_root, config_path)

    # Generate report
    report = generate_verification_report(result, args.format)

    # Output report
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report)
        print(f"Verification report written to: {output_path}")
    else:
        print(report)

    # Exit with appropriate code
    if result.verification_passed:
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
