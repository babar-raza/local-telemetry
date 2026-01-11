#!/usr/bin/env python3
"""Validate telemetry configuration."""

import sys
import os

# Add user site-packages to path
user_site = os.path.expanduser('~\\AppData\\Roaming\\Python\\Python313\\site-packages')
if user_site not in sys.path:
    sys.path.insert(0, user_site)

from src.telemetry.config import TelemetryConfig

def main():
    """Validate configuration and print results."""
    try:
        cfg = TelemetryConfig.from_env()
        is_valid, errors = cfg.validate()

        if not errors:
            print("[PASS] Configuration is Valid!")
            print(f"\nCurrent Configuration:")
            print(f"  TELEMETRY_API_URL: {cfg.api_url}")
            print(f"  GOOGLE_SHEETS_API_ENABLED: {cfg.google_sheets_api_enabled}")
            print(f"  GOOGLE_SHEETS_API_URL: {cfg.google_sheets_api_url or 'Not set'}")
            return 0
        else:
            print("[FAIL] Configuration Validation Failed:")
            for error in errors:
                print(f"  - {error}")
            return 1

    except Exception as e:
        print(f"[ERROR] Error loading configuration: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
