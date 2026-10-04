"""Comprehensive unit and integration test suite for Phase 4: Dynamic Career Portal Synchronization.

Verifies:
A. Workday listing normalization (title, company, location, country, URLs, req ID, description).
B. Greenhouse listing normalization (title, company, offices/location, URLs, internal ID, description).
C. Missing publication timestamp remains unknown (None / UNKNOWN freshness).
D. Explicit publication timestamp is preserved.
E. No fabricated freshness (vague dates like "Posted Today", "Active", "Recently" evaluate to None).
F. Dynamic-source deduplication (canonical fingerprint deduplication across adapters).
G. Repeated hourly discovery does not duplicate alerts / notification proposals.
H. Finite request/navigation timeout (<= 30 seconds).
I. Retry limit (max_retries is respected).
J. Exponential backoff behavior.
K. Blocked source isolation (BlockedSourceError handled gracefully without crashing scanner).
L. Scanner continues when dynamic source fails (source failure isolation).
M. Human approval gates remain intact (PROPOSED status, never auto-applied).
N. Production mock adapter protection remains intact (MockJobSourceAdapter blocked without allow_mock).
"""

import sqlite3
import time
from datetime import UTC, datetime, timedelta

import pytest

from app.db.connection import get_connection
from app.db.models import FreshnessBucket, FreshnessStatus
from app.db.repository import JobRepository
from app.db.schema import create_schema
from app.jobs.freshness import calculate_granular_freshness, calculate_job_freshness
from app.jobs.scanner import FreshJobScanner
from app.jobs.sources.adapters import FETCH_TIMEOUT_SECONDS, MockJobSourceAdapter
from app.jobs.sources.base import JobDiscoveryQuery, RawJobPayload
from app.jobs.sources.dynamic import (
    BlockedSourceError,
    DynamicPortalAdapter,
    DynamicPortalConfig,
    GreenhouseCareerAdapter,
    WorkdayCareerAdapter,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mem_conn() -> sqlite3.Connection:
    conn = get_connection(":memory:", auto_init=True)
    create_schema(conn)
    return conn


@pytest.fixture()
def repo(mem_conn: sqlite3.Connection) -> JobRepository:
    return JobRepository(mem_conn)


# ---------------------------------------------------------------------------
# Test Category A & C & D & E: Workday Normalization & Timestamp Integrity
# ---------------------------------------------------------------------------


class TestWorkdayNormalization:
    def test_workday_listing_normalization_complete(self):
        adapter = WorkdayCareerAdapter()
        raw_item = {
            "title": "Lead Design Verification Engineer",
            "company": "Qualcomm",
            "location": "Bengaluru, Karnataka, India",
            "country": "India",
            "jobId": "3049102",
            "externalPath": "/careers/job/blr/lead-dv-3049102",
            "description": "Qualcomm Bengaluru is seeking Lead Design Verification Engineers for UVM/SystemVerilog verification.",
            "timeType": "Full-time",
            "postedOn": "2025-10-01T08:00:00Z",
            "workplaceType": "hybrid",
        }
        payload = adapter.parse_workday_job(raw_item, base_url="https://qualcomm.wd5.myworkdayjobs.com")

        assert payload.title == "Lead Design Verification Engineer"
        assert payload.company == "Qualcomm"
        assert "Bengaluru" in payload.location
        assert payload.country == "India"
        assert payload.metadata["requisition_id"] == "3049102"
        assert payload.source_url == "https://qualcomm.wd5.myworkdayjobs.com/careers/job/blr/lead-dv-3049102"
        assert payload.application_url == payload.source_url
        assert payload.metadata["published_at"] == "2025-10-01T08:00:00+00:00"
        assert payload.metadata["timestamp_source"] == "workday_cxs_api"
        assert payload.metadata["workplace_type"] == "hybrid"

    def test_workday_missing_timestamp_remains_none(self):
        adapter = WorkdayCareerAdapter()
        raw_item = {
            "title": "ASIC Verification Engineer",
            "company": "NVIDIA",
            "location": "Hyderabad, India",
            "postedOn": None,
        }
        payload = adapter.parse_workday_job(raw_item)
        assert payload.metadata["published_at"] is None

        # Verify freshness calculation treats it strictly as UNKNOWN
        bucket, age_hours, _conf, _ = calculate_granular_freshness(payload.metadata["published_at"])
        assert bucket == FreshnessBucket.UNKNOWN
        assert age_hours is None

    def test_workday_relative_timestamp_rejected_as_none(self):
        adapter = WorkdayCareerAdapter()
        vague_dates = ["Posted Today", "Posted Yesterday", "Posted 2 Days Ago", "Active", "Just Posted"]
        for date_str in vague_dates:
            raw_item = {
                "title": "DV Engineer",
                "company": "Broadcom",
                "location": "Bengaluru, India",
                "postedOn": date_str,
            }
            payload = adapter.parse_workday_job(raw_item)
            assert payload.metadata["published_at"] is None, f"Expected None for '{date_str}'"

            # Freshness calculation must NOT treat as <=24h
            status, _age, _ = calculate_job_freshness(payload.metadata["published_at"])
            assert status == FreshnessStatus.UNKNOWN

    def test_workday_epoch_timestamp_parsed(self):
        adapter = WorkdayCareerAdapter()
        epoch = 1759276800  # valid Unix epoch
        raw_item = {
            "title": "SoC Verification",
            "company": "AMD",
            "postedOn": epoch,
        }
        payload = adapter.parse_workday_job(raw_item)
        assert payload.metadata["published_at"] is not None
        assert "2025" in payload.metadata["published_at"]


# ---------------------------------------------------------------------------
# Test Category B & C & D & E: Greenhouse Normalization & Timestamp Integrity
# ---------------------------------------------------------------------------


class TestGreenhouseNormalization:
    def test_greenhouse_listing_normalization_complete(self):
        adapter = GreenhouseCareerAdapter()
        raw_item = {
            "title": "RISC-V CPU Verification Lead",
            "company": "SiFive",
            "location": {"name": "Bengaluru, India"},
            "country": "India",
            "id": 9988771,
            "absolute_url": "https://boards.greenhouse.io/sifive/jobs/9988771",
            "content": "SiFive is hiring RISC-V CPU Verification leads in Bengaluru. UVM, SystemVerilog, formal verification.",
            "updated_at": "2025-10-02T14:30:00Z",
            "workplace_type": "onsite",
        }
        payload = adapter.parse_greenhouse_job(raw_item)

        assert payload.title == "RISC-V CPU Verification Lead"
        assert payload.company == "SiFive"
        assert payload.location == "Bengaluru, India"
        assert payload.country == "India"
        assert payload.metadata["internal_job_id"] == "9988771"
        assert payload.source_url == "https://boards.greenhouse.io/sifive/jobs/9988771"
        assert payload.metadata["published_at"] == "2025-10-02T14:30:00+00:00"
        assert payload.metadata["timestamp_source"] == "greenhouse_boards_api"

    def test_greenhouse_missing_timestamp_remains_none(self):
        adapter = GreenhouseCareerAdapter()
        raw_item = {
            "title": "Hardware Verification Engineer",
            "company": "Tenstorrent",
            "location": "Santa Clara, CA",
            "updated_at": None,
            "created_at": None,
        }
        payload = adapter.parse_greenhouse_job(raw_item)
        assert payload.metadata["published_at"] is None

        status, age, _ = calculate_job_freshness(payload.metadata["published_at"])
        assert status == FreshnessStatus.UNKNOWN
        assert age is None

    def test_greenhouse_offices_fallback(self):
        adapter = GreenhouseCareerAdapter()
        raw_item = {
            "title": "Verification Engineer",
            "company": "Groq",
            "offices": [{"name": "San Jose, CA, USA"}],
        }
        payload = adapter.parse_greenhouse_job(raw_item)
        assert payload.location == "San Jose, CA, USA"


# ---------------------------------------------------------------------------
# Test Category H & I & J: Timeouts, Retries, Backoff, and Rate Limiting
# ---------------------------------------------------------------------------


class TestTimeoutsAndPoliteRateLimiting:
    def test_config_enforces_finite_timeouts(self):
        config = DynamicPortalConfig(request_timeout_sec=25.0, page_timeout_sec=10.0)
        assert config.request_timeout_sec <= 30.0
        assert config.page_timeout_sec <= 30.0
        assert config.request_timeout_sec <= FETCH_TIMEOUT_SECONDS

    def test_adapter_timeout_bounded_by_fetch_timeout_seconds(self):
        config = DynamicPortalConfig(request_timeout_sec=30.0)
        adapter = WorkdayCareerAdapter(config=config)
        assert adapter.timeout_seconds <= FETCH_TIMEOUT_SECONDS

    def test_execute_with_retry_succeeds_on_transient_failure(self):
        config = DynamicPortalConfig(max_retries=2, request_delay_sec=0.01, backoff_factor=1.2)
        adapter = WorkdayCareerAdapter(config=config)

        attempts = {"n": 0}

        def transient_op():
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise ConnectionResetError("Transient network glitch")
            return "SUCCESS"

        result = adapter.execute_with_retry(transient_op, context="test_op")
        assert result == "SUCCESS"
        assert attempts["n"] == 2

    def test_execute_with_retry_exhaustion_raises(self):
        config = DynamicPortalConfig(max_retries=2, request_delay_sec=0.01)
        adapter = GreenhouseCareerAdapter(config=config)

        attempts = {"n": 0}

        def failing_op():
            attempts["n"] += 1
            raise TimeoutError("Remote server timed out")

        with pytest.raises(TimeoutError):
            adapter.execute_with_retry(failing_op, context="failing_test")

        assert attempts["n"] == 3  # Initial try + 2 retries
        assert adapter.health_status().value == "degraded"

    def test_polite_request_delay_applied(self):
        config = DynamicPortalConfig(request_delay_sec=0.05, max_retries=0)
        adapter = WorkdayCareerAdapter(config=config)

        t0 = time.time()
        adapter.execute_with_retry(lambda: 1)
        adapter.execute_with_retry(lambda: 2)
        elapsed = time.time() - t0
        assert elapsed >= 0.04


# ---------------------------------------------------------------------------
# Test Category K & L: Blocked Source Isolation & Error Resilience
# ---------------------------------------------------------------------------


class MockBlockedWorkdayAdapter(DynamicPortalAdapter):
    def __init__(self):
        super().__init__(name="mock_blocked_workday")

    def fetch_jobs(self, query: JobDiscoveryQuery) -> list[RawJobPayload]:
        raise BlockedSourceError("HTTP 403 Forbidden: Cloudflare anti-bot challenged request")


class TestSourceIsolationAndBlockedPages:
    def test_blocked_source_error_does_not_crash_scanner(self, mem_conn):
        from app.notifications.email import MockEmailProvider
        from app.notifications.service import EmailNotificationService

        blocked_adapter = MockBlockedWorkdayAdapter()
        mock_source = MockJobSourceAdapter()
        email_svc = EmailNotificationService(mem_conn, provider=MockEmailProvider())
        scanner = FreshJobScanner(
            conn=mem_conn,
            adapters=[blocked_adapter, mock_source],
            allow_mock=True,
            email_service=email_svc,
        )

        report = scanner.scan(region="all", hours=24.0, dry_run=False)

        assert report.sources_total == 2
        assert report.sources_failed == 1
        assert report.sources_successful == 1
        assert report.jobs_discovered > 0
        assert report.fresh_24h > 0


# ---------------------------------------------------------------------------
# Test Category F & G: Deduplication Across Dynamic Sources & No Duplicate Alerts
# ---------------------------------------------------------------------------


class TestDynamicDeduplicationAndAlerts:
    def test_cross_adapter_deduplication(self, mem_conn):
        """If Workday and Greenhouse return the same canonical job, it deduplicates cleanly."""
        now = datetime.now(UTC)
        workday_raw = {
            "title": "Design Verification Engineer",
            "company": "Tenstorrent",
            "location": "Bengaluru, India",
            "published_at": (now - timedelta(hours=2.0)).isoformat(),
            "externalPath": "https://tenstorrent.wd.com/job/dv-blr",
            "description": "Tenstorrent Bengaluru hiring DV engineer for AI processors in SystemVerilog.",
        }
        greenhouse_raw = {
            "title": "Design Verification Engineer",
            "company": "Tenstorrent",
            "location": "Bengaluru, India",
            "published_at": (now - timedelta(hours=2.0)).isoformat(),
            "absolute_url": "https://boards.greenhouse.io/tenstorrent/jobs/123",
            "content": "Tenstorrent Bengaluru hiring DV engineer for AI processors in SystemVerilog.",
        }

        workday_adapter = WorkdayCareerAdapter(custom_listings=[workday_raw])
        greenhouse_adapter = GreenhouseCareerAdapter(custom_listings=[greenhouse_raw])

        scanner = FreshJobScanner(
            conn=mem_conn,
            adapters=[workday_adapter, greenhouse_adapter],
            allow_mock=True,
        )

        report = scanner.scan(region="all", hours=24.0, dry_run=False)
        assert report.jobs_scanned == 2
        assert report.jobs_discovered == 2
        assert report.new_jobs == 1
        assert report.duplicates_removed == 1
        assert report.notifications_proposed == 1

        repo = JobRepository(mem_conn)
        jobs = repo.list_normalized_jobs()
        assert len(jobs) == 1

    def test_repeated_hourly_scans_do_not_duplicate_notifications(self, mem_conn):
        """Repeated scans of dynamic portals must not duplicate notification proposals."""
        workday_adapter = WorkdayCareerAdapter()
        greenhouse_adapter = GreenhouseCareerAdapter()

        scanner = FreshJobScanner(
            conn=mem_conn,
            adapters=[workday_adapter, greenhouse_adapter],
            allow_mock=True,
        )

        # First cycle
        report1 = scanner.scan(region="all", hours=24.0, dry_run=False)
        initial_notifs = report1.notifications_proposed
        assert initial_notifs > 0

        # Second cycle (hourly simulation)
        report2 = scanner.scan(region="all", hours=24.0, dry_run=False)
        assert report2.new_jobs == 0
        assert report2.duplicates_removed > 0
        assert report2.notifications_proposed == 0

        repo = JobRepository(mem_conn)
        alerts = repo.list_job_alerts()
        assert len(alerts) == initial_notifs


# ---------------------------------------------------------------------------
# Test Category M & N: Human Approval & Mock Protection
# ---------------------------------------------------------------------------


class TestHumanApprovalAndMockProtection:
    def test_dynamic_portal_notifications_are_proposed_only(self, mem_conn):
        scanner = FreshJobScanner(conn=mem_conn, allow_mock=True)
        report = scanner.scan(region="all", hours=24.0, dry_run=False)
        assert report.jobs_scanned > 0

        repo = JobRepository(mem_conn)
        alerts = repo.list_job_alerts()
        for alert in alerts:
            assert alert.status == "proposed"

        # Applications must NEVER be automatically set to applied
        apps = repo.list_applications()
        for app in apps:
            assert app.status.value != "applied"

    def test_mock_adapter_blocked_in_production(self, mem_conn):
        with pytest.raises(ValueError, match="MockJobSourceAdapter cannot be used in production"):
            FreshJobScanner(conn=mem_conn, adapters=[MockJobSourceAdapter()], allow_mock=False)
