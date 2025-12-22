#!/usr/bin/env python3
"""
Wrapper script to run tests with correct PYTHONPATH.
"""

import sys
from pathlib import Path

# Add user site-packages to path
sys.path.insert(0, r"C:\Users\prora\AppData\Roaming\Python\Python313\site-packages")

# Add src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Get test file from command line
if len(sys.argv) < 2:
    print("Usage: python run_test.py <test_file>")
    sys.exit(1)

test_file = sys.argv[1]

# Run the test
exec(open(test_file).read(), {'__file__': test_file, '__name__': '__main__'})
