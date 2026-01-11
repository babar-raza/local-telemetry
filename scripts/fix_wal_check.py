#!/usr/bin/env python3
"""
Fix WAL autocheckpoint check to be conditional on journal mode.
This script patches validate_installation.py to only enforce WAL autocheckpoint
when journal_mode is WAL, not DELETE.
"""

import sys
from pathlib import Path

# Read the file
script_path = Path(__file__).parent / "validate_installation.py"
content = script_path.read_text()

# Define the old code block
old_code = '''            wal_checkpoint = pragma_cursor.execute("PRAGMA wal_autocheckpoint").fetchone()[0]
            checkpoint_ok = wal_checkpoint == 100
            all_passed &= print_check(
                f"PRAGMA wal_autocheckpoint: {wal_checkpoint}",
                checkpoint_ok,
                "Expected 100 pages to prevent WAL bloat"
            )'''

# Define the new code block
new_code = '''            wal_checkpoint = pragma_cursor.execute("PRAGMA wal_autocheckpoint").fetchone()[0]
            # WAL autocheckpoint only relevant in WAL mode, not DELETE mode
            if journal_mode.lower() == "wal":
                checkpoint_ok = wal_checkpoint == 100
                all_passed &= print_check(
                    f"PRAGMA wal_autocheckpoint: {wal_checkpoint}",
                    checkpoint_ok,
                    "Expected 100 pages to prevent WAL bloat"
                )
            else:
                # In DELETE mode, WAL autocheckpoint is not used
                all_passed &= print_check(
                    f"PRAGMA wal_autocheckpoint: {wal_checkpoint}",
                    True,  # Always pass in non-WAL mode
                    "N/A (using journal_mode=DELETE)"
                )'''

# Apply the patch
if old_code in content:
    content = content.replace(old_code, new_code)
    script_path.write_text(content)
    print("✅ Successfully patched validate_installation.py")
    print("   - WAL autocheckpoint check now conditional on journal_mode")
    sys.exit(0)
else:
    print("❌ Could not find the code block to replace")
    print("   The file may have been already patched or modified")
    sys.exit(1)
