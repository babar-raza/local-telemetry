#!/usr/bin/env python3
"""Analyze production database for agent metrics."""

import sqlite3

db_path = r'D:\agent-metrics\db\telemetry.sqlite'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print('=== PRODUCT/PLATFORM/WEBSITE BREAKDOWN (Top 30) ===')
print()

cursor.execute('''
    SELECT
        agent_name,
        product,
        platform,
        website,
        website_section,
        COUNT(*) as runs,
        SUM(items_discovered) as total_discovered,
        SUM(items_succeeded) as total_succeeded
    FROM agent_runs
    WHERE product IS NOT NULL AND product != ''
    GROUP BY agent_name, product, platform, website, website_section
    ORDER BY runs DESC
    LIMIT 30
''')

results = cursor.fetchall()
for row in results:
    agent = row[0][:35]
    product = row[1][:18] if row[1] else 'N/A'
    platform = row[2][:8] if row[2] else 'N/A'
    website = row[3][:12] if row[3] else 'N/A'
    section = row[4][:12] if row[4] else 'N/A'
    runs = row[5]
    print(f'{agent:<35} | {product:<18} | {platform:<8} | {website:<12} | {section:<12} | {runs:5} runs')

print()
print('=== WEBSITE/SECTION SUMMARY ===')
print()

cursor.execute('''
    SELECT
        website,
        website_section,
        COUNT(*) as runs
    FROM agent_runs
    WHERE website IS NOT NULL
    GROUP BY website, website_section
    ORDER BY runs DESC
''')

for row in cursor.fetchall():
    site = row[0] if row[0] else 'NULL'
    section = row[1] if row[1] else 'NULL'
    runs = row[2]
    print(f'{site:<30} / {section:<20} - {runs:6} runs')

print()
print('=== UNIQUE VALUES SUMMARY ===')
print()

# Unique products
cursor.execute('SELECT DISTINCT product FROM agent_runs WHERE product IS NOT NULL AND product != "" ORDER BY product')
products = [r[0] for r in cursor.fetchall()]
print(f'Unique Products ({len(products)}): {", ".join(products[:20])}{"..." if len(products) > 20 else ""}')

# Unique platforms
cursor.execute('SELECT DISTINCT platform FROM agent_runs WHERE platform IS NOT NULL AND platform != "" ORDER BY platform')
platforms = [r[0] for r in cursor.fetchall()]
print(f'Unique Platforms ({len(platforms)}): {", ".join(platforms)}')

# Unique websites
cursor.execute('SELECT DISTINCT website FROM agent_runs WHERE website IS NOT NULL AND website != "" ORDER BY website')
websites = [r[0] for r in cursor.fetchall()]
print(f'Unique Websites ({len(websites)}): {", ".join(websites)}')

# Unique sections
cursor.execute('SELECT DISTINCT website_section FROM agent_runs WHERE website_section IS NOT NULL AND website_section != "" ORDER BY website_section')
sections = [r[0] for r in cursor.fetchall()]
print(f'Unique Sections ({len(sections)}): {", ".join(sections)}')

conn.close()
