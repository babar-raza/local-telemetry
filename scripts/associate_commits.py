"""
Telemetry Platform - Intelligent Commit Association Script

Associates git commits with telemetry runs using content-based analysis.

Matching strategies (in order of priority):
1. Explicit: Commit message contains "Telemetry-Run-ID: <run_id>"
2. Content-based: Analyzes files changed in commit for translation patterns
   - Detects language codes in paths (/de/, /es/, /fr/, etc.)
   - Matches product_family and subdomain context from telemetry
   - Scores commits by relevance

Time is NOT a factor - commits can come days after the translation run.

Usage:
    python scripts/associate_commits.py                    # Interactive mode
    python scripts/associate_commits.py --auto             # Auto-associate high-confidence matches
    python scripts/associate_commits.py --run-id <id>      # Associate specific run
    python scripts/associate_commits.py --watch            # Watch mode (continuous)
    python scripts/associate_commits.py --dry-run          # Show what would be associated
    python scripts/associate_commits.py --show-commits     # Show available commits for matching

Exit codes:
    0 - Success
    1 - Failure
"""

import os
import sys
import re
import subprocess
import argparse
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional
from dataclasses import dataclass

# Add src to path for importing telemetry package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from telemetry import TelemetryClient
from telemetry.database import DatabaseWriter
from telemetry.config import TelemetryConfig


# ISO 639-1 language codes commonly used in translation
LANGUAGE_CODES = {
    'de', 'es', 'fr', 'it', 'pt', 'nl', 'pl', 'ru', 'ja', 'zh',
    'ko', 'ar', 'hi', 'tr', 'vi', 'th', 'id', 'ms', 'cs', 'sk',
    'hu', 'ro', 'bg', 'uk', 'el', 'he', 'fa', 'sv', 'da', 'no',
    'fi', 'nb', 'nn', 'et', 'lv', 'lt', 'sl', 'hr', 'sr', 'bs',
    'mk', 'sq', 'ka', 'hy', 'az', 'kk', 'uz', 'tg', 'mn', 'ne',
    'bn', 'ta', 'te', 'kn', 'ml', 'si', 'my', 'km', 'lo', 'fil',
    'en',  # Include English as it might be in path comparisons
}

# Pattern to detect language code directories in paths (e.g., /de/, /es/)
LANG_PATH_PATTERN = re.compile(
    r'[/\\](' + '|'.join(LANGUAGE_CODES) + r')[/\\]',
    re.IGNORECASE
)

# Pattern to detect language code in filenames (e.g., index.de.md, _index.es.md)
# Used by blog.aspose.net style: filename.{lang}.md
LANG_FILENAME_PATTERN = re.compile(
    r'[._](' + '|'.join(LANGUAGE_CODES) + r')\.(?:md|html|json|yaml|yml)$',
    re.IGNORECASE
)


@dataclass
class CommitMatch:
    """Represents a potential commit match with scoring."""
    commit: dict
    score: float
    reasons: list[str]
    translated_files: int
    language_codes: set[str]


def parse_iso8601(timestamp_str: str) -> datetime:
    """Parse ISO8601 timestamp to datetime."""
    if timestamp_str.endswith('Z'):
        timestamp_str = timestamp_str[:-1] + '+00:00'

    try:
        return datetime.fromisoformat(timestamp_str)
    except ValueError:
        formats = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(timestamp_str, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        raise ValueError(f"Cannot parse timestamp: {timestamp_str}")


def get_git_repo_path(git_repo_url: str) -> Optional[Path]:
    """Convert git repo URL to local path."""
    if not git_repo_url:
        return None

    # Handle file:// URLs
    if git_repo_url.startswith("file:///"):
        path_str = git_repo_url[8:]
        if len(path_str) > 2 and path_str[1] == ':':
            pass
        elif path_str.startswith("/"):
            path_str = path_str[1:]
        path = Path(path_str)
        if path.exists():
            return path

    # Handle direct paths
    if len(git_repo_url) > 2 and git_repo_url[1] == ':':
        path = Path(git_repo_url)
        if path.exists():
            return path

    # Handle GitHub URLs
    if "github.com" in git_repo_url:
        match = re.search(r'github\.com[/:]([^/]+)/([^/.]+)', git_repo_url)
        if match:
            user, repo = match.groups()
            repo = repo.replace('.git', '')

            username = os.getenv('USERNAME', 'user')
            common_paths = [
                Path(f"D:/repos/{repo}"),
                Path(f"D:/repos/{user}/{repo}"),
                Path(f"C:/repos/{repo}"),
                Path(f"C:/Users/{username}/Documents/GitHub/{repo}"),
                Path(f"C:/Users/{username}/OneDrive/Documents/GitHub/{repo}"),
                Path.home() / "repos" / repo,
                Path.home() / "Documents" / "GitHub" / repo,
                Path.home() / "OneDrive" / "Documents" / "GitHub" / repo,
            ]

            for path in common_paths:
                if path.exists() and (path / ".git").exists():
                    return path

    return None


def get_commit_files(repo_path: Path, commit_hash: str) -> list[str]:
    """Get list of files changed in a commit."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "diff-tree", "--no-commit-id",
             "--name-only", "-r", commit_hash],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return [f for f in result.stdout.strip().split('\n') if f]
    except Exception:
        pass
    return []


def detect_translation_in_files(files: list[str]) -> tuple[int, set[str]]:
    """
    Analyze file paths to detect translation patterns.

    Supports two patterns:
    1. Directory-based: /content/products/slides/de/_index.md (products.aspose.net, kb.aspose.net)
    2. Filename-based: /content/blog/index.de.md (blog.aspose.net)

    Returns:
        tuple: (count of translated files, set of language codes found)
    """
    translated_count = 0
    languages_found = set()

    for file_path in files:
        is_translated = False

        # Pattern 1: Language code in directory path (e.g., /de/, /es/)
        path_matches = LANG_PATH_PATTERN.findall(file_path)
        if path_matches:
            for lang in path_matches:
                lang_lower = lang.lower()
                if lang_lower != 'en':
                    languages_found.add(lang_lower)
                    is_translated = True
                    break

        # Pattern 2: Language code in filename (e.g., index.de.md, _index.es.md)
        if not is_translated:
            filename_match = LANG_FILENAME_PATTERN.search(file_path)
            if filename_match:
                lang_lower = filename_match.group(1).lower()
                if lang_lower != 'en':
                    languages_found.add(lang_lower)
                    is_translated = True

        # Pattern 3: Common translation file patterns
        if not is_translated:
            file_lower = file_path.lower()
            if any(pattern in file_lower for pattern in [
                '_translated', '.translated.', '/translations/',
                '/locales/', '/i18n/', '/l10n/'
            ]):
                is_translated = True

        if is_translated:
            translated_count += 1

    return translated_count, languages_found


def extract_context_from_path(file_path: str) -> dict:
    """
    Extract product family and subdomain hints from file path.

    Path structure examples:
    - content/blog.aspose.net/2024/post/index.de.md
    - content/products.aspose.net/slides/de/_index.md
    - content/kb.aspose.net/cells/net/es/tutorial.md
    """
    context = {
        'product_hints': set(),
        'subdomain_hints': set(),
    }

    path_lower = file_path.lower()

    # Product family detection
    product_patterns = [
        (r'slides', 'slides'),
        (r'cells', 'cells'),
        (r'words', 'words'),
        (r'pdf', 'pdf'),
        (r'email', 'email'),
        (r'imaging', 'imaging'),
        (r'barcode', 'barcode'),
        (r'ocr', 'ocr'),
        (r'cad', 'cad'),
        (r'3d', '3d'),
        (r'html', 'html'),
        (r'tasks', 'tasks'),
        (r'diagram', 'diagram'),
        (r'note', 'note'),
        (r'page', 'page'),
        (r'psd', 'psd'),
        (r'svg', 'svg'),
        (r'tex', 'tex'),
        (r'zip', 'zip'),
        (r'font', 'font'),
        (r'gis', 'gis'),
    ]

    for pattern, product in product_patterns:
        if re.search(pattern, path_lower):
            context['product_hints'].add(product)

    # Subdomain detection from path: content/{subdomain}.aspose.net/...
    # Matches: blog.aspose.net, products.aspose.net, kb.aspose.net, etc.
    subdomain_match = re.search(r'[/\\](\w+)\.aspose\.(?:net|com|cloud)[/\\]', path_lower)
    if subdomain_match:
        context['subdomain_hints'].add(subdomain_match.group(1))

    # Fallback patterns for simpler paths
    subdomain_patterns = [
        (r'[/\\]products[/\\]', 'products'),
        (r'[/\\]docs[/\\]', 'docs'),
        (r'[/\\]reference[/\\]', 'reference'),
        (r'[/\\]kb[/\\]', 'kb'),
        (r'[/\\]blog[/\\]', 'blog'),
        (r'[/\\]purchase[/\\]', 'purchase'),
        (r'[/\\]releases[/\\]', 'releases'),
    ]

    for pattern, subdomain in subdomain_patterns:
        if re.search(pattern, path_lower):
            context['subdomain_hints'].add(subdomain)

    return context


def get_all_commits(repo_path: Path, limit: int = 100, branch: Optional[str] = None) -> list[dict]:
    """Get recent commits from repo (no time filter)."""
    commits = []

    try:
        cmd = [
            "git", "-C", str(repo_path),
            "log",
            f"-{limit}",
            "--format=%H|%an <%ae>|%aI|%s",
            "--no-merges",
        ]

        if branch:
            cmd.append(branch)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return commits

        for line in result.stdout.strip().split('\n'):
            if not line:
                continue

            parts = line.split('|', 3)
            if len(parts) >= 4:
                msg_result = subprocess.run(
                    ["git", "-C", str(repo_path), "log", "-1", "--format=%B", parts[0]],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                full_message = msg_result.stdout.strip() if msg_result.returncode == 0 else parts[3]

                commits.append({
                    "hash": parts[0],
                    "author": parts[1],
                    "timestamp": parts[2],
                    "subject": parts[3],
                    "message": full_message,
                })

    except subprocess.TimeoutExpired:
        print(f"      [WARN] Git command timed out for {repo_path}")
    except FileNotFoundError:
        print(f"      [WARN] Git not found in PATH")
    except Exception as e:
        print(f"      [WARN] Error getting commits: {e}")

    return commits


def score_commit_for_run(
    commit: dict,
    run: dict,
    repo_path: Path,
) -> Optional[CommitMatch]:
    """
    Score how well a commit matches a telemetry run.

    Scoring factors:
    - +100: Explicit Telemetry-Run-ID match
    - +50: Contains translated files (non-English language paths)
    - +20: Product family match
    - +20: Subdomain match
    - +10: Per language code found
    - +5: Hugo-translator pattern in message
    """
    score = 0.0
    reasons = []

    # Check for explicit run ID (highest priority)
    if f"Telemetry-Run-ID: {run['run_id']}" in commit["message"]:
        return CommitMatch(
            commit=commit,
            score=100.0,
            reasons=["Explicit Telemetry-Run-ID match"],
            translated_files=0,
            language_codes=set(),
        )

    # Get files changed in commit
    files = get_commit_files(repo_path, commit["hash"])
    if not files:
        return None

    # Analyze files for translation patterns
    translated_count, languages = detect_translation_in_files(files)

    if translated_count == 0:
        return None  # No translation detected, skip this commit

    score += 50  # Base score for having translated files
    reasons.append(f"Contains {translated_count} translated file(s)")

    score += len(languages) * 10
    if languages:
        reasons.append(f"Languages: {', '.join(sorted(languages))}")

    # Extract context from file paths
    all_context = {'product_hints': set(), 'subdomain_hints': set()}
    for file_path in files:
        ctx = extract_context_from_path(file_path)
        all_context['product_hints'].update(ctx['product_hints'])
        all_context['subdomain_hints'].update(ctx['subdomain_hints'])

    # Match against run context
    run_product = (run.get('product_family') or '').lower()
    run_subdomain = (run.get('subdomain') or '').lower()

    if run_product and run_product in all_context['product_hints']:
        score += 20
        reasons.append(f"Product match: {run_product}")

    if run_subdomain and run_subdomain in all_context['subdomain_hints']:
        score += 20
        reasons.append(f"Subdomain match: {run_subdomain}")

    # Check for agent pattern in message
    if re.match(r'^\[hugo-translator\]', commit["subject"], re.IGNORECASE):
        score += 5
        reasons.append("Hugo-translator commit pattern")

    # Check for translation keywords in message
    msg_lower = commit["subject"].lower()
    if any(kw in msg_lower for kw in ['translat', 'locali', 'i18n', 'l10n']):
        score += 5
        reasons.append("Translation keyword in message")

    return CommitMatch(
        commit=commit,
        score=score,
        reasons=reasons,
        translated_files=translated_count,
        language_codes=languages,
    )


def find_best_commit_match(
    run: dict,
    repo_path: Path,
    branch: Optional[str] = None,
    min_score: float = 50.0,
) -> Optional[CommitMatch]:
    """
    Find the best matching commit for a run.

    Returns the highest-scoring commit above min_score threshold.
    """
    commits = get_all_commits(repo_path, limit=100, branch=branch)

    if not commits:
        return None

    matches = []
    for commit in commits:
        match = score_commit_for_run(commit, run, repo_path)
        if match and match.score >= min_score:
            matches.append(match)

    if not matches:
        return None

    # Return highest scoring match
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[0]


def get_unassociated_runs(db_writer: DatabaseWriter, agent_filter: Optional[str] = None) -> list:
    """Get runs that don't have a commit associated."""
    import sqlite3

    conn = sqlite3.connect(str(db_writer.database_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT run_id, agent_name, start_time, end_time, status,
               git_repo, git_branch, git_commit_hash,
               product_family, subdomain
        FROM agent_runs
        WHERE git_commit_hash IS NULL
          AND git_repo IS NOT NULL
          AND git_repo != ''
          AND status IN ('success', 'partial', 'completed')
    """

    if agent_filter:
        query += f" AND agent_name = ?"
        cursor.execute(query + " ORDER BY start_time DESC", (agent_filter,))
    else:
        cursor.execute(query + " ORDER BY start_time DESC")

    runs = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return runs


def show_available_commits(repo_path: Path, limit: int = 20):
    """Show commits that could be associated."""
    commits = get_all_commits(repo_path, limit=limit)

    print(f"\n   Recent commits in {repo_path}:")
    print("   " + "-" * 60)

    for commit in commits:
        files = get_commit_files(repo_path, commit["hash"])
        translated_count, languages = detect_translation_in_files(files)

        lang_str = f" [{', '.join(sorted(languages))}]" if languages else ""
        trans_str = f" ({translated_count} translated)" if translated_count > 0 else ""

        print(f"   {commit['hash'][:8]} {commit['subject'][:45]}{trans_str}{lang_str}")

    print("   " + "-" * 60)


def associate_commit_interactive(
    client: TelemetryClient,
    run: dict,
    match: CommitMatch,
    auto: bool = False,
    dry_run: bool = False,
) -> bool:
    """Associate a commit with a run, optionally with user confirmation."""

    print(f"\n   Run: {run['run_id']}")
    print(f"   Agent: {run['agent_name']}")
    print(f"   Product: {run.get('product_family', 'N/A')} | Subdomain: {run.get('subdomain', 'N/A')}")
    print(f"   Commit: {match.commit['hash'][:12]}")
    print(f"   Message: {match.commit['subject'][:60]}")
    print(f"   Score: {match.score:.0f} | Files: {match.translated_files}")
    print(f"   Reasons: {', '.join(match.reasons)}")
    if match.language_codes:
        print(f"   Languages: {', '.join(sorted(match.language_codes))}")

    if dry_run:
        print("   [DRY-RUN] Would associate this commit")
        return True

    # Auto-associate only if score is very high
    if auto and match.score < 70:
        print("   [SKIP] Score too low for auto-association (need 70+)")
        return False

    if not auto:
        response = input("   Associate? [y/N]: ").strip().lower()
        if response != 'y':
            print("   Skipped")
            return False

    success, message = client.associate_commit(
        run_id=run['run_id'],
        commit_hash=match.commit['hash'],
        commit_source="manual",
        commit_author=match.commit['author'],
        commit_timestamp=match.commit['timestamp'],
    )

    if success:
        print(f"   [OK] Associated")
    else:
        print(f"   [FAIL] {message}")

    return success


def process_runs(
    client: TelemetryClient,
    runs: list,
    auto: bool = False,
    dry_run: bool = False,
    show_commits: bool = False,
) -> tuple[int, int]:
    """Process runs and find/associate commits."""

    found = 0
    associated = 0

    for run in runs:
        print(f"\n[{run['run_id']}]")

        repo_path = get_git_repo_path(run['git_repo'])
        if not repo_path:
            print(f"   [SKIP] Cannot find local repo for: {run['git_repo']}")
            continue

        print(f"   Repo: {repo_path}")

        if show_commits:
            show_available_commits(repo_path)

        # Find best matching commit
        match = find_best_commit_match(
            run=run,
            repo_path=repo_path,
            branch=run.get('git_branch'),
            min_score=50.0,
        )

        if not match:
            print(f"   [SKIP] No matching commit found (score < 50)")
            continue

        found += 1

        if associate_commit_interactive(client, run, match, auto, dry_run):
            associated += 1

    return found, associated


def watch_mode(client: TelemetryClient, interval: int = 60, auto: bool = False):
    """Continuously watch for new unassociated runs."""

    print(f"[WATCH] Monitoring for unassociated runs (interval: {interval}s)")
    print("[WATCH] Press Ctrl+C to stop\n")

    seen_runs = set()

    try:
        while True:
            runs = get_unassociated_runs(client.database_writer)
            new_runs = [r for r in runs if r['run_id'] not in seen_runs]

            if new_runs:
                print(f"\n[WATCH] Found {len(new_runs)} new unassociated run(s)")
                found, associated = process_runs(client, new_runs, auto=auto)
                print(f"[WATCH] Associated {associated} of {found} found commits")

            for run in runs:
                seen_runs.add(run['run_id'])

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n[WATCH] Stopped")


def main():
    parser = argparse.ArgumentParser(
        description="Intelligently associate git commits with telemetry runs"
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-associate high-confidence matches (score >= 70)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be associated without making changes"
    )
    parser.add_argument(
        "--run-id",
        type=str,
        help="Associate specific run ID"
    )
    parser.add_argument(
        "--commit-hash",
        type=str,
        help="Directly specify commit hash to associate (use with --run-id)"
    )
    parser.add_argument(
        "--agent",
        type=str,
        help="Filter by agent name (e.g., hugo-translator)"
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch mode - continuously monitor for new runs"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Watch interval in seconds (default: 60)"
    )
    parser.add_argument(
        "--show-commits",
        action="store_true",
        help="Show available commits for each repo"
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=50.0,
        help="Minimum score for commit matching (default: 50)"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("Telemetry Platform - Intelligent Commit Association")
    print("=" * 70)

    # Initialize client
    try:
        config = TelemetryConfig.from_env()
        client = TelemetryClient(config)
        print(f"[OK] Connected to database: {config.database_path}")
    except Exception as e:
        print(f"[FAIL] Cannot initialize telemetry: {e}")
        return 1

    if args.watch:
        watch_mode(client, interval=args.interval, auto=args.auto)
        return 0

    # Direct commit hash association
    if args.commit_hash:
        if not args.run_id:
            print("[FAIL] --commit-hash requires --run-id")
            return 1

        run = client.database_writer.get_run(args.run_id)
        if not run:
            print(f"[FAIL] Run not found: {args.run_id}")
            return 1

        if run.git_commit_hash:
            print(f"[SKIP] Run already has commit: {run.git_commit_hash}")
            return 0

        repo_path = get_git_repo_path(run.git_repo)
        if repo_path:
            try:
                result = subprocess.run(
                    ["git", "-C", str(repo_path), "log", "-1",
                     "--format=%H|%an <%ae>|%aI|%s", args.commit_hash],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0 and result.stdout.strip():
                    parts = result.stdout.strip().split('|', 3)
                    commit_author = parts[1] if len(parts) > 1 else None
                    commit_timestamp = parts[2] if len(parts) > 2 else None
                else:
                    commit_author = None
                    commit_timestamp = None
            except Exception:
                commit_author = None
                commit_timestamp = None
        else:
            commit_author = None
            commit_timestamp = None

        print(f"\n[INFO] Associating commit {args.commit_hash[:12]} with run {args.run_id}")

        if args.dry_run:
            print("[DRY-RUN] Would associate this commit")
            return 0

        success, message = client.associate_commit(
            run_id=args.run_id,
            commit_hash=args.commit_hash,
            commit_source="manual",
            commit_author=commit_author,
            commit_timestamp=commit_timestamp,
        )

        if success:
            print(f"[OK] {message}")
            return 0
        else:
            print(f"[FAIL] {message}")
            return 1

    # Get runs to process
    if args.run_id:
        run = client.database_writer.get_run(args.run_id)
        if not run:
            print(f"[FAIL] Run not found: {args.run_id}")
            return 1
        runs = [{
            'run_id': run.run_id,
            'agent_name': run.agent_name,
            'start_time': run.start_time,
            'end_time': run.end_time,
            'status': run.status,
            'git_repo': run.git_repo,
            'git_branch': run.git_branch,
            'git_commit_hash': run.git_commit_hash,
            'product_family': run.product_family,
            'subdomain': run.subdomain,
        }]
        if runs[0]['git_commit_hash']:
            print(f"[SKIP] Run already has commit: {runs[0]['git_commit_hash']}")
            return 0
    else:
        runs = get_unassociated_runs(client.database_writer, agent_filter=args.agent)

    if not runs:
        print("\n[OK] No unassociated runs found")
        return 0

    print(f"\n[INFO] Found {len(runs)} unassociated run(s)")

    # Process runs
    found, associated = process_runs(
        client, runs,
        auto=args.auto,
        dry_run=args.dry_run,
        show_commits=args.show_commits,
    )

    # Summary
    print("\n" + "=" * 70)
    print(f"[SUMMARY] Processed {len(runs)} runs")
    print(f"          Found {found} matching commits")
    print(f"          Associated {associated} commits")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
