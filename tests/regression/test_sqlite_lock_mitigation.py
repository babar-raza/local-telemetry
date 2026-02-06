"""Regression test: SQLite lock mitigation is applied to server DB connections.

Why this exists
--------------
Agents intermittently observed "database is locked" errors when multiple writers
or short-lived contention occurred. The primary mitigation in this repo's
documented production decision is setting a non-trivial busy_timeout while using
DELETE journal mode.

This test asserts that get_db() applies the configured PRAGMA busy_timeout
(and journal_mode/synchronous) on the connection it yields.

This would FAIL on older versions where PRAGMA busy_timeout was not consistently
applied (default is typically 0ms).
"""

from __future__ import annotations

import importlib
import sys


def _fresh_import(module_name: str):
    """Import a module in a fresh state (best-effort) so env var overrides apply."""
    if module_name in sys.modules:
        del sys.modules[module_name]
    return importlib.import_module(module_name)


def test_get_db_applies_busy_timeout_and_pragmas(monkeypatch, tmp_path):
    # Arrange: configure a temp DB path and explicit PRAGMA values.
    db_path = tmp_path / "telemetry.sqlite"

    monkeypatch.setenv("TELEMETRY_DB_PATH", str(db_path))
    monkeypatch.setenv("TELEMETRY_DB_JOURNAL_MODE", "DELETE")
    monkeypatch.setenv("TELEMETRY_DB_SYNCHRONOUS", "FULL")

    expected_busy_timeout_ms = 12345
    monkeypatch.setenv("TELEMETRY_DB_BUSY_TIMEOUT_MS", str(expected_busy_timeout_ms))

    # Ensure connect() itself is willing to wait, too.
    monkeypatch.setenv("TELEMETRY_DB_CONNECT_TIMEOUT_SECONDS", "30")

    # Keep retry settings deterministic for this unit test.
    monkeypatch.setenv("TELEMETRY_DB_MAX_RETRIES", "0")
    monkeypatch.setenv("TELEMETRY_DB_RETRY_BASE_DELAY_SECONDS", "0")

    # Force a fresh import so TelemetryAPIConfig reads env vars at import time.
    _fresh_import("telemetry.config")
    telemetry_service = _fresh_import("telemetry_service")

    # Act: open a connection using the same code path the server uses.
    with telemetry_service.get_db() as conn:
        actual_timeout = int(conn.execute("PRAGMA busy_timeout").fetchone()[0])
        actual_journal = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        actual_sync = int(conn.execute("PRAGMA synchronous").fetchone()[0])

    # Assert
    assert actual_timeout == expected_busy_timeout_ms
    assert actual_journal == "delete"

    # SQLite returns numeric constants for synchronous (0=OFF,1=NORMAL,2=FULL,3=EXTRA)
    assert actual_sync == 2
