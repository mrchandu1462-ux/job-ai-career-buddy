"""Phase 3 — Tests for ScannerDaemon (continuous monitor scheduler).

Tests use an in-memory SQLite database and monkeypatched scan execution so
no real-time waiting or network I/O is required.

Verified properties
-------------------
- ScannerDaemon rejects invalid constructor arguments.
- run_once() delegates to FreshJobScanner.scan() with correct parameters.
- run_once() raises RuntimeError when the scanner is locked.
- Continuous run() terminates cleanly after a SIGINT-equivalent flag.
- Cycle statistics (completed / failed) increment correctly.
- State is persisted to monitor_state after each cycle.
- Dry-run mode does NOT write to monitor_state.
- Scheduler status from repository reflects daemon state accurately.
- monitor_state table is created by create_schema().
- get_scheduler_status() returns sane defaults when no state is present.
- set_monitor_state_value() is idempotent (upsert semantics).
- Stale-lock recovery still works alongside scheduler state.
- run_once() respects the region, hours, and limit arguments.
- ScannerDaemon with --once equivalent terminates after one cycle.
- Daemon PID is persisted correctly.
- Repeated hourly discovery does not create duplicate notification proposals.
- Network adapters have explicit finite timeouts <= 30s.
"""

import os
import signal
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from app.db.connection import get_connection
from app.db.repository import JobRepository
from app.db.schema import create_schema
from app.jobs.scanner import FreshJobScanner, ScanReport
from app.jobs.scheduler import (
    DEFAULT_INTERVAL_MINUTES,
    SCAN_LIMIT,
    SCAN_MIN_SCORE,
    SCAN_WINDOW_HOURS,
    ScannerDaemon,
)
from app.jobs.sources.adapters import (
    FETCH_TIMEOUT_SECONDS,
    FeedJobSourceAdapter,
    MockJobSourceAdapter,
    SemiconductorCareerPageAdapter,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mem_conn() -> sqlite3.Connection:
    """Fresh in-memory DB with full schema (including monitor_state)."""
    conn = get_connection(":memory:", auto_init=True)
    return conn


@pytest.fixture()
def repo(mem_conn: sqlite3.Connection) -> JobRepository:
    return JobRepository(mem_conn)


def _make_report(**kwargs) -> ScanReport:
    """Build a minimal ScanReport with sensible defaults for testing."""
    defaults = {
        "timestamp": "2025-01-01T00:00:00+00:00",
        "region": "all",
        "window_hours": SCAN_WINDOW_HOURS,
        "sources_total": 2,
        "sources_successful": 2,
        "sources_failed": 0,
        "jobs_scanned": 5,
        "jobs_discovered": 5,
        "new_jobs": 3,
        "fresh_24h": 2,
        "india_count": 3,
        "overseas_count": 2,
        "critical_matches": 1,
        "high_matches": 1,
        "duplicates_removed": 0,
        "notifications_proposed": 1,
        "duration_ms": 120.0,
        "discovered_jobs": [],
    }
    defaults.update(kwargs)
    return ScanReport(**defaults)


def _make_mock_scanner(report: ScanReport | None = None) -> MagicMock:
    """Create a mock FreshJobScanner that returns a fixed ScanReport."""
    scanner = MagicMock()
    scanner.scan.return_value = report or _make_report()
    return scanner


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


class TestScannerDaemonConstructor:
    def test_default_construction(self, mem_conn):
        daemon = ScannerDaemon(conn=mem_conn)
        assert daemon.interval_minutes == DEFAULT_INTERVAL_MINUTES
        assert daemon.region == "all"
        assert daemon.dry_run is False

    def test_custom_interval(self, mem_conn):
        daemon = ScannerDaemon(conn=mem_conn, interval_minutes=30)
        assert daemon.interval_minutes == 30

    def test_invalid_interval_zero(self, mem_conn):
        with pytest.raises(ValueError, match="interval_minutes must be >= 1"):
            ScannerDaemon(conn=mem_conn, interval_minutes=0)

    def test_invalid_interval_negative(self, mem_conn):
        with pytest.raises(ValueError, match="interval_minutes must be >= 1"):
            ScannerDaemon(conn=mem_conn, interval_minutes=-5)

    def test_valid_regions(self, mem_conn):
        for region in ("all", "india", "overseas"):
            daemon = ScannerDaemon(conn=mem_conn, region=region)
            assert daemon.region == region

    def test_invalid_region(self, mem_conn):
        with pytest.raises(ValueError, match="region must be"):
            ScannerDaemon(conn=mem_conn, region="europe")

    def test_dry_run_flag(self, mem_conn):
        daemon = ScannerDaemon(conn=mem_conn, dry_run=True)
        assert daemon.dry_run is True

    def test_scanner_injection(self, mem_conn):
        mock_scanner = _make_mock_scanner()
        daemon = ScannerDaemon(conn=mem_conn, scanner=mock_scanner)
        assert daemon._scanner is mock_scanner


# ---------------------------------------------------------------------------
# run_once() delegation
# ---------------------------------------------------------------------------


class TestRunOnce:
    def test_run_once_calls_scan_with_correct_args(self, mem_conn):
        report = _make_report(region="india", fresh_24h=3)
        mock_scanner = _make_mock_scanner(report)
        daemon = ScannerDaemon(conn=mem_conn, region="india", scanner=mock_scanner)

        result = daemon.run_once()

        mock_scanner.scan.assert_called_once_with(
            region="india",
            hours=SCAN_WINDOW_HOURS,
            dry_run=False,
            min_score=SCAN_MIN_SCORE,
            limit=SCAN_LIMIT,
        )
        assert result is report

    def test_run_once_dry_run_forwarded(self, mem_conn):
        mock_scanner = _make_mock_scanner()
        daemon = ScannerDaemon(conn=mem_conn, dry_run=True, scanner=mock_scanner)

        daemon.run_once()

        _, kwargs = mock_scanner.scan.call_args
        assert kwargs.get("dry_run") is True

    def test_run_once_region_all(self, mem_conn):
        mock_scanner = _make_mock_scanner()
        daemon = ScannerDaemon(conn=mem_conn, region="all", scanner=mock_scanner)

        daemon.run_once()

        _, kwargs = mock_scanner.scan.call_args
        assert kwargs.get("region") == "all"

    def test_run_once_raises_on_locked_scanner(self, mem_conn):
        mock_scanner = MagicMock()
        mock_scanner.scan.side_effect = RuntimeError("Scanner lock already held by another process.")
        daemon = ScannerDaemon(conn=mem_conn, scanner=mock_scanner)

        with pytest.raises(RuntimeError, match="Scanner lock already held"):
            daemon.run_once()

    def test_run_once_overseas_region(self, mem_conn):
        mock_scanner = _make_mock_scanner()
        daemon = ScannerDaemon(conn=mem_conn, region="overseas", scanner=mock_scanner)

        daemon.run_once()

        _, kwargs = mock_scanner.scan.call_args
        assert kwargs.get("region") == "overseas"


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


class TestStatePersistence:
    def test_save_state_running_true(self, mem_conn, repo):
        mock_scanner = _make_mock_scanner()
        daemon = ScannerDaemon(conn=mem_conn, scanner=mock_scanner)
        daemon._save_state(running=True)

        assert repo.get_monitor_state_value("scheduler_running") == "true"

    def test_save_state_running_false(self, mem_conn, repo):
        mock_scanner = _make_mock_scanner()
        daemon = ScannerDaemon(conn=mem_conn, scanner=mock_scanner)
        daemon._save_state(running=False)

        assert repo.get_monitor_state_value("scheduler_running") == "false"

    def test_save_state_persists_pid(self, mem_conn, repo):
        daemon = ScannerDaemon(conn=mem_conn, scanner=_make_mock_scanner())
        daemon._save_state(running=True)

        stored_pid = repo.get_monitor_state_value("daemon_pid")
        assert stored_pid == str(os.getpid())

    def test_save_state_persists_interval(self, mem_conn, repo):
        daemon = ScannerDaemon(conn=mem_conn, interval_minutes=45, scanner=_make_mock_scanner())
        daemon._save_state(running=True)

        assert repo.get_monitor_state_value("interval_minutes") == "45"

    def test_save_state_persists_region(self, mem_conn, repo):
        daemon = ScannerDaemon(conn=mem_conn, region="india", scanner=_make_mock_scanner())
        daemon._save_state(running=True)

        assert repo.get_monitor_state_value("scheduler_region") == "india"

    def test_save_state_persists_cycles_completed(self, mem_conn, repo):
        daemon = ScannerDaemon(conn=mem_conn, scanner=_make_mock_scanner())
        daemon._cycles_completed = 7
        daemon._save_state(running=True)

        assert repo.get_monitor_state_value("cycles_completed") == "7"

    def test_save_state_persists_cycles_failed(self, mem_conn, repo):
        daemon = ScannerDaemon(conn=mem_conn, scanner=_make_mock_scanner())
        daemon._cycles_failed = 2
        daemon._save_state(running=True)

        assert repo.get_monitor_state_value("cycles_failed") == "2"

    def test_save_state_persists_last_cycle_at(self, mem_conn, repo):
        daemon = ScannerDaemon(conn=mem_conn, scanner=_make_mock_scanner())
        ts = "2025-06-01T10:00:00+00:00"
        daemon._save_state(running=True, last_cycle_at=ts)

        assert repo.get_monitor_state_value("last_cycle_at") == ts

    def test_save_state_persists_next_cycle_at(self, mem_conn, repo):
        daemon = ScannerDaemon(conn=mem_conn, scanner=_make_mock_scanner())
        ts = "2025-06-01T11:00:00+00:00"
        daemon._save_state(running=True, next_cycle_at=ts)

        assert repo.get_monitor_state_value("next_cycle_at") == ts

    def test_dry_run_does_not_write_state(self, mem_conn, repo):
        """dry_run=True must not write anything to monitor_state."""
        daemon = ScannerDaemon(conn=mem_conn, dry_run=True, scanner=_make_mock_scanner())
        daemon._save_state(running=True)

        assert repo.get_monitor_state_value("scheduler_running") is None


# ---------------------------------------------------------------------------
# Continuous run() loop behaviour
# ---------------------------------------------------------------------------


class TestRunLoop:
    def test_run_stops_on_shutdown_flag(self, mem_conn):
        """Setting _shutdown_requested before run() means the loop exits immediately."""
        mock_scanner = _make_mock_scanner()
        daemon = ScannerDaemon(conn=mem_conn, scanner=mock_scanner, interval_minutes=1)

        sleep_count = {"n": 0}

        def fake_sleep(seconds: float) -> None:
            sleep_count["n"] += 1
            daemon._shutdown_requested = True  # Signal shutdown on first tick

        with patch("app.jobs.scheduler.time.sleep", side_effect=fake_sleep):
            rc = daemon.run()

        assert rc == 0
        assert daemon._cycles_completed == 1

    def test_run_increments_completed_on_success(self, mem_conn):
        mock_scanner = _make_mock_scanner()
        daemon = ScannerDaemon(conn=mem_conn, scanner=mock_scanner, interval_minutes=1)

        def fake_sleep(_):
            daemon._shutdown_requested = True

        with patch("app.jobs.scheduler.time.sleep", side_effect=fake_sleep):
            daemon.run()

        assert daemon._cycles_completed == 1
        assert daemon._cycles_failed == 0
        assert daemon._consecutive_failures == 0

    def test_run_increments_failed_on_scan_error(self, mem_conn):
        mock_scanner = MagicMock()
        mock_scanner.scan.side_effect = ValueError("Simulated scan failure")
        daemon = ScannerDaemon(conn=mem_conn, scanner=mock_scanner, interval_minutes=1)

        def fake_sleep(_):
            daemon._shutdown_requested = True

        with patch("app.jobs.scheduler.time.sleep", side_effect=fake_sleep):
            daemon.run()

        assert daemon._cycles_failed == 1
        assert daemon._consecutive_failures == 1
        assert daemon._cycles_completed == 0

    def test_run_skips_locked_cycle_without_failing(self, mem_conn):
        """RuntimeError from lock contention should NOT count as a failure."""
        mock_scanner = MagicMock()
        mock_scanner.scan.side_effect = RuntimeError("Scanner lock already held by another process.")
        daemon = ScannerDaemon(conn=mem_conn, scanner=mock_scanner, interval_minutes=1)

        def fake_sleep(_):
            daemon._shutdown_requested = True

        with patch("app.jobs.scheduler.time.sleep", side_effect=fake_sleep):
            daemon.run()

        assert daemon._cycles_failed == 0
        assert daemon._cycles_completed == 0

    def test_run_sets_running_false_on_shutdown(self, mem_conn):
        mock_scanner = _make_mock_scanner()
        daemon = ScannerDaemon(conn=mem_conn, scanner=mock_scanner, interval_minutes=1)

        def fake_sleep(_):
            daemon._shutdown_requested = True

        with patch("app.jobs.scheduler.time.sleep", side_effect=fake_sleep):
            daemon.run()

        repo = JobRepository(mem_conn)
        assert repo.get_monitor_state_value("scheduler_running") == "false"

    def test_run_two_cycles(self, mem_conn):
        """Daemon completes exactly 2 cycles before shutdown is requested."""
        mock_scanner = _make_mock_scanner()
        daemon = ScannerDaemon(conn=mem_conn, scanner=mock_scanner, interval_minutes=1)

        tick_count = {"n": 0}

        def fake_sleep(_):
            tick_count["n"] += 1
            if tick_count["n"] >= 60 * 2:
                daemon._shutdown_requested = True

        with patch("app.jobs.scheduler.time.sleep", side_effect=fake_sleep):
            daemon.run()

        assert daemon._cycles_completed == 2

    def test_run_returns_zero_on_clean_exit(self, mem_conn):
        daemon = ScannerDaemon(conn=mem_conn, scanner=_make_mock_scanner(), interval_minutes=1)

        def fake_sleep(_):
            daemon._shutdown_requested = True

        with patch("app.jobs.scheduler.time.sleep", side_effect=fake_sleep):
            rc = daemon.run()

        assert rc == 0

    def test_signal_handler_sets_shutdown_requested(self, mem_conn):
        daemon = ScannerDaemon(conn=mem_conn, scanner=_make_mock_scanner())
        assert daemon._shutdown_requested is False
        daemon._handle_signal(signal.SIGINT, None)
        assert daemon._shutdown_requested is True


# ---------------------------------------------------------------------------
# Repository: monitor_state CRUD
# ---------------------------------------------------------------------------


class TestMonitorStateRepository:
    def test_get_missing_key_returns_none(self, repo):
        assert repo.get_monitor_state_value("nonexistent_key") is None

    def test_set_and_get_value(self, repo):
        repo.set_monitor_state_value("test_key", "hello")
        assert repo.get_monitor_state_value("test_key") == "hello"

    def test_upsert_overwrites_existing(self, repo):
        repo.set_monitor_state_value("test_key", "first")
        repo.set_monitor_state_value("test_key", "second")
        assert repo.get_monitor_state_value("test_key") == "second"

    def test_multiple_keys_independent(self, repo):
        repo.set_monitor_state_value("key_a", "alpha")
        repo.set_monitor_state_value("key_b", "beta")
        assert repo.get_monitor_state_value("key_a") == "alpha"
        assert repo.get_monitor_state_value("key_b") == "beta"


# ---------------------------------------------------------------------------
# Repository: get_scheduler_status()
# ---------------------------------------------------------------------------


class TestGetSchedulerStatus:
    def test_defaults_when_no_state(self, repo):
        status = repo.get_scheduler_status()
        assert status["is_running"] is False
        assert status["last_cycle_at"] is None
        assert status["next_cycle_at"] is None
        assert status["cycles_completed"] == 0
        assert status["cycles_failed"] == 0
        assert status["consecutive_failures"] == 0
        assert status["daemon_pid"] is None
        assert status["interval_minutes"] == 60
        assert status["region"] == "all"
        assert status["jobs_discovered"] == 0
        assert status["fresh_jobs"] == 0

    def test_reflects_running_true(self, repo):
        repo.set_monitor_state_value("scheduler_running", "true")
        status = repo.get_scheduler_status()
        assert status["is_running"] is True

    def test_reflects_running_false(self, repo):
        repo.set_monitor_state_value("scheduler_running", "false")
        status = repo.get_scheduler_status()
        assert status["is_running"] is False

    def test_reflects_cycles_completed(self, repo):
        repo.set_monitor_state_value("cycles_completed", "12")
        status = repo.get_scheduler_status()
        assert status["cycles_completed"] == 12

    def test_reflects_cycles_failed(self, repo):
        repo.set_monitor_state_value("cycles_failed", "3")
        status = repo.get_scheduler_status()
        assert status["cycles_failed"] == 3

    def test_reflects_daemon_pid(self, repo):
        repo.set_monitor_state_value("daemon_pid", "98765")
        status = repo.get_scheduler_status()
        assert status["daemon_pid"] == 98765

    def test_reflects_interval_minutes(self, repo):
        repo.set_monitor_state_value("interval_minutes", "30")
        status = repo.get_scheduler_status()
        assert status["interval_minutes"] == 30

    def test_reflects_region(self, repo):
        repo.set_monitor_state_value("scheduler_region", "overseas")
        status = repo.get_scheduler_status()
        assert status["region"] == "overseas"

    def test_reflects_last_cycle_at(self, repo):
        ts = "2025-07-15T08:30:00+00:00"
        repo.set_monitor_state_value("last_cycle_at", ts)
        status = repo.get_scheduler_status()
        assert status["last_cycle_at"] == ts

    def test_reflects_next_cycle_at(self, repo):
        ts = "2025-07-15T09:30:00+00:00"
        repo.set_monitor_state_value("next_cycle_at", ts)
        status = repo.get_scheduler_status()
        assert status["next_cycle_at"] == ts

    def test_reflects_job_counts(self, repo):
        repo.set_monitor_state_value("last_jobs_discovered", "42")
        repo.set_monitor_state_value("last_fresh_24h", "15")
        repo.set_monitor_state_value("last_india_count", "10")
        repo.set_monitor_state_value("last_overseas_count", "5")
        status = repo.get_scheduler_status()
        assert status["jobs_discovered"] == 42
        assert status["fresh_jobs"] == 15
        assert status["india_jobs"] == 10
        assert status["overseas_jobs"] == 5


# ---------------------------------------------------------------------------
# Schema: monitor_state table exists after create_schema
# ---------------------------------------------------------------------------


class TestMonitorStateSchema:
    def test_monitor_state_table_created(self, mem_conn):
        cursor = mem_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='monitor_state';"
        )
        row = cursor.fetchone()
        assert row is not None, "monitor_state table must exist after schema init"

    def test_monitor_state_table_idempotent(self, mem_conn):
        """Running create_schema twice must not raise an error."""
        create_schema(mem_conn)  # Second call
        cursor = mem_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='monitor_state';"
        )
        assert cursor.fetchone() is not None

    def test_monitor_state_columns(self, mem_conn):
        cursor = mem_conn.execute("PRAGMA table_info(monitor_state);")
        cols = {row["name"] for row in cursor.fetchall()}
        assert "key" in cols
        assert "value" in cols
        assert "updated_at" in cols

    def test_key_is_primary_key(self, mem_conn):
        """key column must be PRIMARY KEY (no duplicate keys allowed)."""
        mem_conn.execute("INSERT INTO monitor_state (key, value, updated_at) VALUES ('k', 'v', '2025-01-01')")
        mem_conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            mem_conn.execute("INSERT INTO monitor_state (key, value, updated_at) VALUES ('k', 'v2', '2025-01-01')")
            mem_conn.commit()


# ---------------------------------------------------------------------------
# Integration: full daemon cycle writes state readable by get_scheduler_status
# ---------------------------------------------------------------------------


class TestSchedulerIntegration:
    def test_full_cycle_state_readable_via_repo(self, mem_conn):
        mock_scanner = _make_mock_scanner()
        daemon = ScannerDaemon(conn=mem_conn, scanner=mock_scanner, interval_minutes=1, region="india")

        def fake_sleep(_):
            daemon._shutdown_requested = True

        with patch("app.jobs.scheduler.time.sleep", side_effect=fake_sleep):
            daemon.run()

        repo = JobRepository(mem_conn)
        status = repo.get_scheduler_status()

        assert status["is_running"] is False  # Daemon has stopped.
        assert status["cycles_completed"] == 1
        assert status["cycles_failed"] == 0
        assert status["region"] == "india"
        assert status["interval_minutes"] == 1
        assert status["daemon_pid"] == os.getpid()

    def test_run_once_does_not_mutate_running_state(self, mem_conn):
        """run_once() is stateless — it should not write scheduler_running."""
        mock_scanner = _make_mock_scanner()
        daemon = ScannerDaemon(conn=mem_conn, scanner=mock_scanner)

        daemon.run_once()

        repo = JobRepository(mem_conn)
        # scheduler_running should never have been set by run_once().
        assert repo.get_monitor_state_value("scheduler_running") is None


# ---------------------------------------------------------------------------
# Deduplication and Network Timeout Tests
# ---------------------------------------------------------------------------


class TestDeduplicationAndNetworkHardening:
    def test_repeated_discovery_does_not_duplicate_notifications(self, mem_conn):
        """Running multiple scans on identical listings must NOT duplicate alert proposals."""
        mock_adapter = MockJobSourceAdapter()
        scanner = FreshJobScanner(conn=mem_conn, adapters=[mock_adapter], allow_mock=True)

        report1 = scanner.scan(region="all", hours=24.0, dry_run=False)
        assert report1.new_jobs > 0
        assert report1.notifications_proposed > 0
        initial_notifications = report1.notifications_proposed

        # Run second scan with identical listings
        report2 = scanner.scan(region="all", hours=24.0, dry_run=False)
        assert report2.new_jobs == 0
        assert report2.duplicates_removed > 0
        # No new notification proposals generated
        assert report2.notifications_proposed == 0

        repo = JobRepository(mem_conn)
        alerts = repo.list_job_alerts()
        # Verify alert count didn't double
        assert len(alerts) == initial_notifications

    def test_network_adapters_have_finite_timeout(self):
        """All production adapters must expose finite timeout_seconds <= 30."""
        assert FETCH_TIMEOUT_SECONDS <= 30

        adapters = [
            SemiconductorCareerPageAdapter(),
            FeedJobSourceAdapter(),
            MockJobSourceAdapter(),
        ]
        for adapter in adapters:
            assert hasattr(adapter, "timeout_seconds")
            assert adapter.timeout_seconds <= 30
            assert adapter.timeout_seconds > 0
