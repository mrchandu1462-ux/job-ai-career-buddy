"""Deterministic test suite for Phase 2 Production Scanner Lock and Database Verification."""

from datetime import UTC, datetime, timedelta

import pytest

from app.db.connection import get_connection
from app.db.repository import JobRepository
from app.db.schema import create_schema
from app.jobs.scanner import FreshJobScanner
from app.jobs.sources.adapters import JobSourceAdapter, MockJobSourceAdapter
from app.jobs.sources.base import JobDiscoveryQuery, RawJobPayload


class FailingAdapter(JobSourceAdapter):
    """Adapter that intentionally raises an unhandled exception during job fetching."""

    @property
    def adapter_name(self) -> str:
        return "failing_adapter"

    @property
    def source_category(self) -> str:
        return "career_pages"

    def fetch_jobs(self, query: JobDiscoveryQuery) -> list[RawJobPayload]:
        raise ConnectionResetError("Remote API disconnected abruptly")

    def supports_region(self, region: str) -> bool:
        return True

    def supports_freshness(self) -> bool:
        return True


class DummySuccessAdapter(JobSourceAdapter):
    """Adapter that returns empty payloads cleanly without remote network access."""

    @property
    def adapter_name(self) -> str:
        return "dummy_success_adapter"

    @property
    def source_category(self) -> str:
        return "career_pages"

    def fetch_jobs(self, query: JobDiscoveryQuery) -> list[RawJobPayload]:
        return []

    def supports_region(self, region: str) -> bool:
        return True

    def supports_freshness(self) -> bool:
        return True


# -----------------------------------------------------------------------------
# Database Schema & Idempotency Tests
# -----------------------------------------------------------------------------

def test_scanner_lock_table_exists_and_schema_valid():
    """Verify scanner_locks table exists and has exact schema columns after initialization."""
    conn = get_connection(":memory:")
    cursor = conn.execute("PRAGMA table_info(scanner_locks);")
    columns = {row["name"]: row["type"].upper() for row in cursor.fetchall()}

    assert "lock_name" in columns
    assert "owner" in columns
    assert "acquired_at" in columns
    assert "lease_seconds" in columns

    assert columns["lock_name"] == "TEXT"
    assert columns["owner"] == "TEXT"
    assert columns["acquired_at"] == "TEXT"
    assert columns["lease_seconds"] == "INTEGER"


def test_scanner_lock_schema_idempotent_and_preserves_data():
    """Verify that re-running schema initialization is idempotent and preserves table data."""
    conn = get_connection(":memory:")
    repo = JobRepository(conn)

    # Insert a lock record
    inserted = repo.acquire_scanner_lock("test_lock", "test_owner", lease_seconds=300)
    assert inserted is True

    # Re-run schema initialization twice
    create_schema(conn)
    create_schema(conn)

    # Confirm data is preserved
    row = conn.execute("SELECT * FROM scanner_locks WHERE lock_name = 'test_lock';").fetchone()
    assert row is not None
    assert row["owner"] == "test_owner"
    assert row["lease_seconds"] == 300


# -----------------------------------------------------------------------------
# Lock Acquisition, Ownership & Rejection Tests
# -----------------------------------------------------------------------------

def test_acquire_lock_successfully():
    """First process acquires the named lock successfully."""
    conn = get_connection(":memory:")
    repo = JobRepository(conn)

    acquired = repo.acquire_scanner_lock("fresh_job_scanner", "process_1234", lease_seconds=300)
    assert acquired is True

    row = conn.execute("SELECT * FROM scanner_locks WHERE lock_name = 'fresh_job_scanner';").fetchone()
    assert row is not None
    assert row["owner"] == "process_1234"
    assert row["lease_seconds"] == 300


def test_second_acquisition_rejected_while_active():
    """Second process cannot acquire the same lock while the active lease is valid."""
    conn = get_connection(":memory:")
    repo = JobRepository(conn)

    # First acquisition
    first = repo.acquire_scanner_lock("fresh_job_scanner", "owner_alpha", lease_seconds=300)
    assert first is True

    # Second acquisition attempt with different owner
    second = repo.acquire_scanner_lock("fresh_job_scanner", "owner_beta", lease_seconds=300)
    assert second is False

    # Verify original owner still owns the lock
    row = conn.execute("SELECT * FROM scanner_locks WHERE lock_name = 'fresh_job_scanner';").fetchone()
    assert row["owner"] == "owner_alpha"


def test_wrong_owner_cannot_release_lock():
    """Process with mismatched owner identifier cannot release another process's lock."""
    conn = get_connection(":memory:")
    repo = JobRepository(conn)

    repo.acquire_scanner_lock("fresh_job_scanner", "legitimate_owner", lease_seconds=300)

    # Impostor attempts release
    repo.release_scanner_lock("fresh_job_scanner", "impostor_owner")

    # Lock must still be held
    row = conn.execute("SELECT * FROM scanner_locks WHERE lock_name = 'fresh_job_scanner';").fetchone()
    assert row is not None
    assert row["owner"] == "legitimate_owner"

    # Legitimate owner releases lock
    repo.release_scanner_lock("fresh_job_scanner", "legitimate_owner")
    row_after = conn.execute("SELECT * FROM scanner_locks WHERE lock_name = 'fresh_job_scanner';").fetchone()
    assert row_after is None


# -----------------------------------------------------------------------------
# Stale Lock & Lease Policy Tests
# -----------------------------------------------------------------------------

def test_active_lock_is_not_treated_as_stale():
    """An active lock well within lease duration cannot be claimed by another process."""
    conn = get_connection(":memory:")
    repo = JobRepository(conn)

    # Simulate a lock acquired 60 seconds ago with 300 second lease
    acquired_time = (datetime.now(UTC) - timedelta(seconds=60)).isoformat()
    conn.execute(
        "INSERT INTO scanner_locks (lock_name, owner, acquired_at, lease_seconds) VALUES (?, ?, ?, ?)",
        ("fresh_job_scanner", "active_worker", acquired_time, 300),
    )
    conn.commit()

    # Second process tries to acquire
    acquired = repo.acquire_scanner_lock("fresh_job_scanner", "new_worker", lease_seconds=300)
    assert acquired is False

    row = conn.execute("SELECT owner FROM scanner_locks WHERE lock_name = 'fresh_job_scanner';").fetchone()
    assert row["owner"] == "active_worker"


def test_stale_lock_recovery_after_lease_expiry():
    """A stale lock exceeding lease duration is recovered cleanly by a new owner."""
    conn = get_connection(":memory:")
    repo = JobRepository(conn)

    # Simulate a crashed process lock acquired 301 seconds ago with 300s lease
    stale_time = (datetime.now(UTC) - timedelta(seconds=305)).isoformat()
    conn.execute(
        "INSERT INTO scanner_locks (lock_name, owner, acquired_at, lease_seconds) VALUES (?, ?, ?, ?)",
        ("fresh_job_scanner", "dead_pid_9999", stale_time, 300),
    )
    conn.commit()

    # New owner acquires and recovers the lock
    recovered = repo.acquire_scanner_lock("fresh_job_scanner", "alive_pid_1234", lease_seconds=300)
    assert recovered is True

    row = conn.execute("SELECT * FROM scanner_locks WHERE lock_name = 'fresh_job_scanner';").fetchone()
    assert row["owner"] == "alive_pid_1234"


# -----------------------------------------------------------------------------
# Scanner Execution Lifecycle Tests (Success, Exception, Dry Run, Mocks)
# -----------------------------------------------------------------------------

def test_successful_scan_releases_lock():
    """Normal successful scan execution guarantees the lock is released in finally block."""
    conn = get_connection(":memory:")
    adapter = DummySuccessAdapter()
    scanner = FreshJobScanner(conn=conn, adapters=[adapter])

    report = scanner.scan(region="all", hours=24.0, dry_run=False)
    assert report.sources_successful == 1

    # Verify lock has been completely released
    row = conn.execute("SELECT * FROM scanner_locks WHERE lock_name = 'fresh_job_scanner';").fetchone()
    assert row is None


def test_scan_exception_releases_lock(monkeypatch):
    """Scanner exceptions guarantee the lock is released in finally block."""
    conn = get_connection(":memory:")
    adapter = DummySuccessAdapter()
    scanner = FreshJobScanner(conn=conn, adapters=[adapter])

    def boom(*args, **kwargs):
        raise RuntimeError("Fatal unexpected database or pipeline crash")

    monkeypatch.setattr(scanner, "_process_raw_payload", boom)

    # Set up adapter to return 1 payload so _process_raw_payload is invoked
    adapter.fetch_jobs = lambda query: [
        RawJobPayload(
            source_name="test",
            source_job_id="1",
            title="DV Engineer",
            company="TestCo",
            location="Bengaluru",
            raw_description="DV role",
        )
    ]

    # Run scan which will hit the exception
    report = scanner.scan(region="all", hours=24.0, dry_run=False)
    # The scanner isolates per-adapter failures, so report has sources_failed
    assert report.sources_failed == 1

    # Lock must still be released
    row = conn.execute("SELECT * FROM scanner_locks WHERE lock_name = 'fresh_job_scanner';").fetchone()
    assert row is None


def test_adapter_failure_releases_lock():
    """Adapter failure within scan cycle is isolated and scanner lock is released."""
    conn = get_connection(":memory:")
    failing = FailingAdapter()
    scanner = FreshJobScanner(conn=conn, adapters=[failing])

    report = scanner.scan(region="all", hours=24.0, dry_run=False)
    assert report.sources_failed == 1

    row = conn.execute("SELECT * FROM scanner_locks WHERE lock_name = 'fresh_job_scanner';").fetchone()
    assert row is None



def test_fatal_unhandled_exception_releases_lock(monkeypatch):
    """Even if an unhandled exception escapes the scan loop, finally block guarantees release."""
    conn = get_connection(":memory:")
    adapter = DummySuccessAdapter()
    scanner = FreshJobScanner(conn=conn, adapters=[adapter])

    def catastrophic_failure(*args, **kwargs):
        raise MemoryError("Out of memory simulation")

    monkeypatch.setattr("time.perf_counter", catastrophic_failure)

    with pytest.raises(MemoryError):
        scanner.scan(region="all", hours=24.0, dry_run=False)

    # Lock must still be released
    row = conn.execute("SELECT * FROM scanner_locks WHERE lock_name = 'fresh_job_scanner';").fetchone()
    assert row is None


def test_dry_run_respects_scanner_lock():
    """Dry-run mode acquires and respects scanner lock and releases upon completion."""
    conn = get_connection(":memory:")
    repo = JobRepository(conn)

    # Manually hold lock
    repo.acquire_scanner_lock("fresh_job_scanner", "external_lock_holder", lease_seconds=300)

    adapter = DummySuccessAdapter()
    scanner = FreshJobScanner(conn=conn, adapters=[adapter])

    # Scanner in dry_run mode must be blocked
    with pytest.raises(RuntimeError) as excinfo:
        scanner.scan(region="all", hours=24.0, dry_run=True)
    assert "Scanner lock already held" in str(excinfo.value)

    # Release manual lock
    repo.release_scanner_lock("fresh_job_scanner", "external_lock_holder")

    # Scanner in dry_run mode now succeeds and releases lock
    report = scanner.scan(region="all", hours=24.0, dry_run=True)
    assert report.sources_successful == 1

    # Lock is released after dry run
    row = conn.execute("SELECT * FROM scanner_locks WHERE lock_name = 'fresh_job_scanner';").fetchone()
    assert row is None


def test_production_mock_job_source_adapter_blocked_unless_explicit():
    """Production FreshJobScanner strictly blocks MockJobSourceAdapter unless allow_mock=True."""
    conn = get_connection(":memory:")
    mock_adapter = MockJobSourceAdapter()

    # Blocked by default
    with pytest.raises(ValueError) as excinfo:
        FreshJobScanner(conn=conn, adapters=[mock_adapter], allow_mock=False)
    assert "MockJobSourceAdapter cannot be used in production scans" in str(excinfo.value)

    # Blocked on registration
    scanner = FreshJobScanner(conn=conn, adapters=[DummySuccessAdapter()], allow_mock=False)
    with pytest.raises(ValueError) as excinfo:
        scanner.register_adapter(mock_adapter)
    assert "MockJobSourceAdapter cannot be used in production scans" in str(excinfo.value)

    # Allowed when explicitly declared for test
    test_scanner = FreshJobScanner(conn=conn, adapters=[mock_adapter], allow_mock=True)
    assert len(test_scanner.adapters) == 1


def test_releasing_already_released_lock_is_safe_and_idempotent():
    """Releasing an unheld or already-released lock is idempotent and does not error."""
    conn = get_connection(":memory:")
    repo = JobRepository(conn)

    # Releasing non-existent lock should not raise
    repo.release_scanner_lock("fresh_job_scanner", "nobody")

    # Acquire, release once, then release again
    repo.acquire_scanner_lock("fresh_job_scanner", "owner_1", lease_seconds=300)
    repo.release_scanner_lock("fresh_job_scanner", "owner_1")
    repo.release_scanner_lock("fresh_job_scanner", "owner_1")

    row = conn.execute("SELECT * FROM scanner_locks WHERE lock_name = 'fresh_job_scanner';").fetchone()
    assert row is None


def test_two_independent_scanner_processes_simulation(monkeypatch):
    """Simulate two independent scanner processes (with distinct PIDs). Second is rejected while first is scanning."""
    conn = get_connection(":memory:")
    scanner2 = FreshJobScanner(conn=conn, adapters=[DummySuccessAdapter()])
    scanner2_result: dict[str, str] = {}

    class MidScanAdapter(JobSourceAdapter):
        @property
        def adapter_name(self) -> str:
            return "mid_scan_adapter"

        @property
        def source_category(self) -> str:
            return "career_pages"

        def supports_region(self, region: str) -> bool:
            return True

        def supports_freshness(self) -> bool:
            return True

        def fetch_jobs(self, query: JobDiscoveryQuery) -> list[RawJobPayload]:
            # While scanner 1 holds lock, scanner 2 tries to scan as PID 20002
            monkeypatch.setattr("os.getpid", lambda: 20002)
            try:
                scanner2.scan(region="all", hours=24.0, dry_run=False)
                scanner2_result["status"] = "unexpected_success"
            except RuntimeError as e:
                scanner2_result["status"] = "blocked"
                scanner2_result["error"] = str(e)
            return []

    # Scanner 1 starts with PID 10001
    monkeypatch.setattr("os.getpid", lambda: 10001)
    scanner1 = FreshJobScanner(conn=conn, adapters=[MidScanAdapter()])
    report1 = scanner1.scan(region="all", hours=24.0, dry_run=False)

    assert report1.sources_successful == 1
    assert scanner2_result.get("status") == "blocked"
    assert "Scanner lock already held" in scanner2_result.get("error", "")

    # Now that scanner 1 is done, scanner 2 can scan cleanly
    monkeypatch.setattr("os.getpid", lambda: 20002)
    report2 = scanner2.scan(region="all", hours=24.0, dry_run=False)
    assert report2.sources_successful == 1


def test_schema_initialization_on_fresh_temp_db(tmp_path):
    """Verify schema initialization on a fresh SQLite disk database creates scanner_locks in WAL mode."""
    db_file = tmp_path / "fresh_init.db"
    conn = get_connection(db_file)
    try:
        # Check WAL mode
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert journal_mode.lower() == "wal"

        # Check scanner_locks table
        cursor = conn.execute("PRAGMA table_info(scanner_locks);")
        cols = {row["name"]: row["type"].upper() for row in cursor.fetchall()}
        assert "lock_name" in cols
        assert "owner" in cols
        assert "acquired_at" in cols
        assert "lease_seconds" in cols
    finally:
        conn.close()


def test_cli_scan_respects_lock_and_exits_cleanly(monkeypatch, capsys, tmp_path):
    """CLI scan cleanly exits with non-zero code (1) when another scanner holds the lock."""
    from app.jobs.scan import main as cli_scan_main

    test_db = tmp_path / "cli_lock_test.db"
    conn = get_connection(test_db)
    repo = JobRepository(conn)
    repo.acquire_scanner_lock("fresh_job_scanner", "cli_test_lock_holder", lease_seconds=300)
    conn.close()

    monkeypatch.setattr("app.jobs.scan.get_db_connection", lambda: get_connection(test_db))
    monkeypatch.setattr("sys.argv", ["scan.py", "--region", "all", "--hours", "24", "--dry-run"])
    exit_code = cli_scan_main()
    captured = capsys.readouterr().out
    assert exit_code == 1
    assert "SCANNER LOCKED" in captured

    # Verify lock is still held by original holder
    conn2 = get_connection(test_db)
    row = conn2.execute("SELECT owner FROM scanner_locks WHERE lock_name = 'fresh_job_scanner';").fetchone()
    assert row["owner"] == "cli_test_lock_holder"
    conn2.close()


