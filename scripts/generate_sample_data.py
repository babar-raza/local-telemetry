"""
Generate sample telemetry data for testing weekly sheets integration.

This script creates realistic test data simulating multiple agents working
across different websites, products, and platforms over a week.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import sqlite3
from datetime import datetime, timedelta, timezone
from telemetry.client import TelemetryClient
from telemetry.config import TelemetryConfig
from telemetry.models import get_iso8601_timestamp
from telemetry.schema import create_schema


def generate_sample_data(db_path: str):
    """Generate sample telemetry data for testing."""

    # Set up environment for test database
    import os
    os.environ["TELEMETRY_DB_PATH"] = db_path
    os.environ["METRICS_API_ENABLED"] = "false"  # Don't post to API
    os.environ["TELEMETRY_SKIP_VALIDATION"] = "true"  # Skip validation since we're creating dirs

    # Create database schema first
    print("Creating database schema...")
    success, messages = create_schema(db_path)
    if not success:
        print("ERROR: Failed to create schema:")
        for msg in messages:
            print(f"  {msg}")
        return
    print("Schema created successfully\n")

    # Create config from environment
    config = TelemetryConfig.from_env()

    client = TelemetryClient(config)

    # Sample agents and their typical work patterns
    agents = [
        {
            "agent_name": "KB Article Writer",
            "job_type": "KB Article Generation",
            "website": "aspose.com",
            "website_section": "KB",
            "products": [
                ("Aspose.Slides", ".NET", "slides"),
                ("Aspose.Words", ".NET", "words"),
                ("Aspose.Cells", "Java", "cells"),
                ("GroupDocs.Signature", "Java", "signature"),
            ],
            "agent_owner": "Tahir Manzoor",
        },
        {
            "agent_name": "Docs Translator",
            "job_type": "Translation",
            "website": "aspose.com",
            "website_section": "Docs",
            "products": [
                ("Aspose.PDF", "Python", "pdf"),
                ("Aspose.Cells", ".NET", "cells"),
            ],
            "agent_owner": "Translation Team",
        },
        {
            "agent_name": "SEO Optimizer",
            "job_type": "SEO Updates",
            "website": "groupdocs.com",
            "website_section": "Blog",
            "products": [
                ("GroupDocs.Viewer", ".NET", "viewer"),
                ("GroupDocs.Parser", "Java", "parser"),
            ],
            "agent_owner": "SEO Team",
        },
        {
            "agent_name": "Code Generator",
            "job_type": "Sample Code Generation",
            "website": None,  # Test NULL handling
            "website_section": None,
            "products": [
                ("Aspose.Slides", ".NET", None),
                (None, None, None),  # Test all NULL
            ],
            "agent_owner": "Dev Team",
        },
    ]

    # Generate runs over the past 7 days
    base_time = datetime.now(timezone.utc) - timedelta(days=7)

    print("Generating sample telemetry data...")

    run_count = 0
    for day in range(7):
        day_time = base_time + timedelta(days=day)

        # Each agent works on some products each day
        for agent in agents:
            # Agents don't work every day
            if day % 2 == 0 and agent["agent_name"] == "SEO Optimizer":
                continue  # SEO works every other day

            # Work on subset of products each day
            num_products = min(2, len(agent["products"]))
            for i, (product, platform, family) in enumerate(agent["products"][:num_products]):
                # Create run
                run_id = client.start_run(
                    agent_name=agent["agent_name"],
                    job_type=agent["job_type"],
                    trigger_type="scheduler",
                    agent_owner=agent["agent_owner"],
                    website=agent["website"],
                    website_section=agent["website_section"],
                    product=product,
                    platform=platform,
                    product_family=family,
                )

                # Simulate work with random success/failure
                import random
                items_discovered = random.randint(5, 20)
                items_failed = random.randint(0, 3)
                items_succeeded = items_discovered - items_failed

                # Some runs have errors
                error_summary = None
                if items_failed > 0:
                    error_summary = f"Failed to process {items_failed} items"

                status = "success" if items_failed == 0 else "success"  # All success for testing

                # End run
                client.end_run(
                    run_id,
                    status=status,
                    items_discovered=items_discovered,
                    items_succeeded=items_succeeded,
                    items_failed=items_failed,
                    error_summary=error_summary,
                )

                run_count += 1

    print(f"[OK] Generated {run_count} sample runs")

    # Show summary
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("\n[DATA SUMMARY]")
    print("-" * 60)

    # Runs by agent
    cursor.execute("""
        SELECT agent_name, COUNT(*) as run_count
        FROM agent_runs
        GROUP BY agent_name
        ORDER BY run_count DESC
    """)
    print("\nRuns by Agent:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} runs")

    # Runs by status
    cursor.execute("""
        SELECT status, COUNT(*) as run_count
        FROM agent_runs
        GROUP BY status
    """)
    print("\nRuns by Status:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} runs")

    # Runs with NULL fields
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN website IS NULL THEN 1 ELSE 0 END) as null_website,
            SUM(CASE WHEN product IS NULL THEN 1 ELSE 0 END) as null_product,
            SUM(CASE WHEN platform IS NULL THEN 1 ELSE 0 END) as null_platform,
            SUM(CASE WHEN product_family IS NULL THEN 1 ELSE 0 END) as null_family
        FROM agent_runs
    """)
    row = cursor.fetchone()
    print("\nRuns with NULL fields:")
    print(f"  Total runs: {row[0]}")
    print(f"  NULL website: {row[1]}")
    print(f"  NULL product: {row[2]}")
    print(f"  NULL platform: {row[3]}")
    print(f"  NULL product_family: {row[4]}")

    # Sample aggregation preview
    cursor.execute("""
        SELECT
            agent_name,
            COALESCE(website, 'NA') as website,
            COALESCE(website_section, 'NA') as section,
            COALESCE(product_family, 'NA') as family,
            COUNT(*) as run_count,
            SUM(items_discovered) as total_discovered,
            SUM(items_succeeded) as total_succeeded,
            SUM(items_failed) as total_failed
        FROM agent_runs
        WHERE status = 'success'
        GROUP BY agent_name, website, website_section, product_family
        ORDER BY run_count DESC
        LIMIT 10
    """)
    print("\n[SAMPLE AGGREGATION - Top 10 Groups]")
    print("-" * 60)
    print(f"{'Agent':<25} {'Website':<15} {'Section':<10} {'Family':<10} Runs  Items")
    print("-" * 60)
    for row in cursor.fetchall():
        agent, website, section, family, runs, disc, succ, fail = row
        print(f"{agent:<25} {website:<15} {section:<10} {family:<10} {runs:>4}  {disc:>4} disc, {succ:>4} succ, {fail:>4} fail")

    conn.close()

    print("\n[OK] Sample data generation complete!")
    print(f"[OK] Database: {db_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate sample telemetry data")
    parser.add_argument(
        "--db",
        default="data/test_telemetry.db",
        help="Path to test database (default: data/test_telemetry.db)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete existing database before generating new data",
    )

    args = parser.parse_args()

    db_path = Path(args.db)

    # Clean existing database if requested
    if args.clean and db_path.exists():
        print(f"[OK] Removing existing database: {db_path}")
        db_path.unlink()

    # Ensure directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate data
    generate_sample_data(str(db_path))
