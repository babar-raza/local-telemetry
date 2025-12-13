#!/usr/bin/env python3
"""
TodoWrite Update Monitor

Monitors TodoWrite update patterns to detect batched updates and ensure
real-time status tracking. Analyzes timing patterns and alerts on batching.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class TodoUpdate:
    """Represents a single TodoWrite update."""
    timestamp: datetime
    task_id: str
    old_status: str
    new_status: str
    line_number: int


@dataclass
class BatchEvent:
    """Represents a detected batch update event."""
    start_time: datetime
    end_time: datetime
    updates: List[TodoUpdate]
    duration_seconds: float

    @property
    def task_count(self) -> int:
        return len(self.updates)


def parse_update_log(log_path: Path) -> List[TodoUpdate]:
    """
    Parse TodoWrite update log to extract updates with timestamps.

    Expected log format:
    2025-12-11 14:30:22 - Task: day5-task3, Status: in_progress → completed
    """
    updates = []

    if not log_path.exists():
        return updates

    timestamp_pattern = r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})'
    update_pattern = r'Task:\s+([^,]+),\s+Status:\s+(\w+)\s*→\s*(\w+)'

    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                # Extract timestamp
                ts_match = re.search(timestamp_pattern, line)
                if not ts_match:
                    continue

                timestamp = datetime.strptime(ts_match.group(1), '%Y-%m-%d %H:%M:%S')

                # Extract update details
                update_match = re.search(update_pattern, line)
                if not update_match:
                    continue

                updates.append(TodoUpdate(
                    timestamp=timestamp,
                    task_id=update_match.group(1).strip(),
                    old_status=update_match.group(2).strip(),
                    new_status=update_match.group(3).strip(),
                    line_number=line_num
                ))

    except Exception as e:
        print(f"Warning: Error parsing log file: {e}", file=sys.stderr)

    return updates


def detect_batched_updates(
    updates: List[TodoUpdate],
    threshold_seconds: int = 5
) -> List[BatchEvent]:
    """
    Detect batched updates (multiple updates within threshold seconds).

    Args:
        updates: List of TodoWrite updates
        threshold_seconds: Time window for batching detection

    Returns:
        List of detected batch events
    """
    if not updates:
        return []

    # Sort by timestamp
    sorted_updates = sorted(updates, key=lambda u: u.timestamp)

    batches = []
    current_batch = [sorted_updates[0]]

    for update in sorted_updates[1:]:
        time_diff = (update.timestamp - current_batch[-1].timestamp).total_seconds()

        if time_diff <= threshold_seconds:
            # Part of current batch
            current_batch.append(update)
        else:
            # Save current batch if it has multiple updates
            if len(current_batch) > 1:
                batches.append(BatchEvent(
                    start_time=current_batch[0].timestamp,
                    end_time=current_batch[-1].timestamp,
                    updates=current_batch.copy(),
                    duration_seconds=(current_batch[-1].timestamp - current_batch[0].timestamp).total_seconds()
                ))

            # Start new batch
            current_batch = [update]

    # Check final batch
    if len(current_batch) > 1:
        batches.append(BatchEvent(
            start_time=current_batch[0].timestamp,
            end_time=current_batch[-1].timestamp,
            updates=current_batch.copy(),
            duration_seconds=(current_batch[-1].timestamp - current_batch[0].timestamp).total_seconds()
        ))

    return batches


def analyze_update_timing(updates: List[TodoUpdate]) -> dict:
    """Analyze timing patterns in updates."""
    if not updates:
        return {
            'total_updates': 0,
            'time_span_hours': 0,
            'avg_update_interval_seconds': 0,
            'max_gap_seconds': 0,
            'min_gap_seconds': 0
        }

    sorted_updates = sorted(updates, key=lambda u: u.timestamp)

    # Calculate time span
    time_span = sorted_updates[-1].timestamp - sorted_updates[0].timestamp
    time_span_hours = time_span.total_seconds() / 3600

    # Calculate gaps between updates
    gaps = []
    for i in range(1, len(sorted_updates)):
        gap = (sorted_updates[i].timestamp - sorted_updates[i-1].timestamp).total_seconds()
        gaps.append(gap)

    avg_gap = sum(gaps) / len(gaps) if gaps else 0
    max_gap = max(gaps) if gaps else 0
    min_gap = min(gaps) if gaps else 0

    return {
        'total_updates': len(updates),
        'time_span_hours': round(time_span_hours, 2),
        'avg_update_interval_seconds': round(avg_gap, 2),
        'max_gap_seconds': round(max_gap, 2),
        'min_gap_seconds': round(min_gap, 2)
    }


def generate_monitoring_report(
    updates: List[TodoUpdate],
    batches: List[BatchEvent],
    log_path: Path,
    threshold_seconds: int
) -> str:
    """Generate monitoring report."""
    timing_analysis = analyze_update_timing(updates)

    report = []
    report.append("=" * 70)
    report.append("TODOWRITE UPDATE MONITORING REPORT")
    report.append("=" * 70)
    report.append(f"Log file: {log_path}")
    report.append(f"Batching threshold: {threshold_seconds} seconds")
    report.append("")

    report.append("SUMMARY")
    report.append("-" * 70)
    report.append(f"Total updates: {timing_analysis['total_updates']}")
    report.append(f"Time span: {timing_analysis['time_span_hours']} hours")
    report.append(f"Average update interval: {timing_analysis['avg_update_interval_seconds']} seconds")
    report.append(f"Detected batch events: {len(batches)}")
    report.append("")

    if batches:
        report.append("⚠️  BATCHED UPDATE EVENTS DETECTED")
        report.append("-" * 70)
        report.append("")

        for i, batch in enumerate(batches, 1):
            report.append(f"Batch Event #{i}")
            report.append(f"  Time: {batch.start_time} - {batch.end_time}")
            report.append(f"  Duration: {batch.duration_seconds:.1f} seconds")
            report.append(f"  Updates: {batch.task_count} tasks")
            report.append("")
            report.append("  Tasks:")
            for update in batch.updates:
                report.append(f"    - {update.task_id}: {update.old_status} → {update.new_status}")
            report.append("")

        report.append("RECOMMENDATION")
        report.append("-" * 70)
        report.append("Batched updates reduce real-time visibility into task progress.")
        report.append("Update TodoWrite immediately after completing each task:")
        report.append("")
        report.append("  ✓ GOOD: Complete task 1 → Update TodoWrite → Complete task 2 → Update TodoWrite")
        report.append("  ✗ BAD:  Complete task 1, 2, 3 → Update TodoWrite for all")
        report.append("")
    else:
        report.append("✓ NO BATCHING DETECTED")
        report.append("-" * 70)
        report.append("All updates are properly spaced. Good real-time tracking!")
        report.append("")

    # Recent updates
    if updates:
        report.append("RECENT UPDATES")
        report.append("-" * 70)
        recent = sorted(updates, key=lambda u: u.timestamp, reverse=True)[:10]
        for update in recent:
            report.append(f"{update.timestamp} - {update.task_id}: {update.old_status} → {update.new_status}")
        report.append("")

    report.append("=" * 70)

    return '\n'.join(report)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Monitor TodoWrite update patterns",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--log-file',
        type=Path,
        required=True,
        help='Path to TodoWrite update log'
    )

    parser.add_argument(
        '--threshold',
        type=int,
        default=5,
        help='Batch detection threshold in seconds (default: 5)'
    )

    parser.add_argument(
        '--report',
        type=Path,
        help='Save monitoring report to file'
    )

    parser.add_argument(
        '--format',
        choices=['text', 'json'],
        default='text',
        help='Output format (default: text)'
    )

    parser.add_argument(
        '--alert-on-batching',
        action='store_true',
        help='Exit with code 1 if batching detected'
    )

    args = parser.parse_args()

    # Parse updates from log
    print(f"Analyzing TodoWrite updates: {args.log_file}")
    updates = parse_update_log(args.log_file)

    if not updates:
        print("No updates found in log file")
        return 0

    print(f"Found {len(updates)} updates")

    # Detect batching
    batches = detect_batched_updates(updates, args.threshold)

    # Generate report
    report = generate_monitoring_report(
        updates,
        batches,
        args.log_file,
        args.threshold
    )

    # Output report
    if args.format == 'text':
        print(report)
    elif args.format == 'json':
        timing_analysis = analyze_update_timing(updates)
        json_report = {
            'log_file': str(args.log_file),
            'threshold_seconds': args.threshold,
            'timing_analysis': timing_analysis,
            'batch_events': [
                {
                    'start_time': batch.start_time.isoformat(),
                    'end_time': batch.end_time.isoformat(),
                    'duration_seconds': batch.duration_seconds,
                    'task_count': batch.task_count,
                    'tasks': [u.task_id for u in batch.updates]
                }
                for batch in batches
            ]
        }
        print(json.dumps(json_report, indent=2))

    # Save report if requested
    if args.report:
        with open(args.report, 'w') as f:
            f.write(report)
        print(f"\nReport saved to: {args.report}")

    # Exit code based on batching detection
    if args.alert_on_batching and batches:
        return 1  # Alert: batching detected
    else:
        return 0  # No alert


if __name__ == '__main__':
    sys.exit(main())
