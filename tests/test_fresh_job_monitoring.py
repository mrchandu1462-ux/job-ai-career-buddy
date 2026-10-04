"""Comprehensive unit and integration test suite for Phase 5: Fresh Job Monitoring & Alert Engine.

Verifies:
1. Freshness calculations (<6h, 6-24h, >24h, unknown timestamps, invalid formats)
2. Geographic classification (India tech hubs vs Overseas markets)
3. Workplace & Visa sponsorship extraction (zero fabrication)
4. Alert priority calculation (P0, P1, P2, P3, UNKNOWN)
5. Adapter architecture and failure isolation
6. Cross-source deduplication and source reference merging
7. 7D matching integration and fresher fit
8. Alert deduplication (preventing duplicate proposals)
9. Human-gated notification creation (PROPOSED status, no auto-apply)
10. Dry-run safety (zero persistence / zero side effects)
11. SQLite schema migration and idempotency
12. CLI entrypoint invocation
"""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from app.career.notifications import (
    NotificationDispatchStatus,
    ScheduleNotificationService,
)
from app.db.repository import JobRepository
from app.db.schema import create_tables
from app.jobs.freshness import (
    calculate_alert_priority,
    calculate_job_freshness,
    classify_geography,
    extract_visa_sponsorship,
    extract_workplace_type,
)
from app.jobs.models import (
    AlertPriority,
    FreshnessStatus,
    JobAlertRecord,
    JobSourceRunRecord,
    VisaSponsorshipStatus,
    WorkplaceType,
)
from app.jobs.monitor import main as cli_main
from app.jobs.monitoring_service import FreshJobMonitoringService
from app.jobs.normalizer import normalize_job_listing
from app.jobs.sources.adapters import (
    JobSourceAdapter,
    MockJobSourceAdapter,
)
from app.jobs.sources.base import JobDiscoveryQuery, RawJobPayload
from app.profile.loader import load_candidate_profile, load_fact_bank


@pytest.fixture
def in_memory_db() -> sqlite3.Connection:
    """Provide an isolated in-memory SQLite database with initialized schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_tables(conn)
    return conn


@pytest.fixture
def candidate_context():
    """Load canonical profile and fact bank."""
    profile = load_candidate_profile()
    fact_bank = load_fact_bank()
    return profile, fact_bank


# -----------------------------------------------------------------------------
# 1. Freshness Calculation Tests
# -----------------------------------------------------------------------------
class TestFreshnessCalculation:
    def test_fresh_0_6_hours(self):
        now = datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC)
        pub_time = (now - timedelta(hours=3)).isoformat()
        status, age_hours, conf = calculate_job_freshness(pub_time, now=now)
        assert status == FreshnessStatus.FRESH_0_6_HOURS
        assert age_hours == pytest.approx(3.0, 0.1)
        assert conf == 1.0

    def test_fresh_6_24_hours(self):
        now = datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC)
        pub_time = (now - timedelta(hours=14)).isoformat()
        status, age_hours, conf = calculate_job_freshness(pub_time, now=now)
        assert status == FreshnessStatus.FRESH_6_24_HOURS
        assert age_hours == pytest.approx(14.0, 0.1)
        assert conf == 1.0

    def test_recent_1_3_days(self):
        now = datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC)
        pub_time = (now - timedelta(days=2)).isoformat()
        status, age_hours, _conf = calculate_job_freshness(pub_time, now=now)
        assert status == FreshnessStatus.RECENT_1_3_DAYS
        assert age_hours == pytest.approx(48.0, 0.1)

    def test_older_than_3_days(self):
        now = datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC)
        pub_time = (now - timedelta(days=10)).isoformat()
        status, age_hours, _conf = calculate_job_freshness(pub_time, now=now)
        assert status == FreshnessStatus.OLDER
        assert age_hours == pytest.approx(240.0, 0.1)

    def test_unknown_timestamp_is_never_fabricated(self):
        status, age_hours, conf = calculate_job_freshness(None)
        assert status == FreshnessStatus.UNKNOWN
        assert age_hours is None
        assert conf == 0.0

    def test_invalid_string_timestamp_gracefully_handled(self):
        status, age_hours, _conf = calculate_job_freshness("invalid-date-format")
        assert status == FreshnessStatus.UNKNOWN
        assert age_hours is None



# -----------------------------------------------------------------------------
# 2. Geographic & Attribute Extraction Tests
# -----------------------------------------------------------------------------
class TestGeographicAndAttributes:
    def test_india_priority_hub_classification(self):
        res = classify_geography(location="Bengaluru, Karnataka", country="India")
        assert res["market_region"] == "India"
        assert res["is_india"] is True
        assert res["priority_hub"] == "Bengaluru"
        assert res["country"] == "India"

    def test_overseas_classification(self):
        res = classify_geography(location="San Jose, CA", country="United States")
        assert res["is_overseas"] is True
        assert res["country"] == "United States"

    def test_workplace_type_extraction(self):
        assert extract_workplace_type("Full-time hybrid role 3 days in office") == WorkplaceType.HYBRID.value
        assert extract_workplace_type("100% remote opportunity anywhere in India") == WorkplaceType.REMOTE.value
        assert extract_workplace_type("On-site lab position at semiconductor fab") == WorkplaceType.ONSITE.value
        assert extract_workplace_type("General job description without mention") == WorkplaceType.UNKNOWN.value

    def test_visa_sponsorship_zero_fabrication(self):
        assert extract_visa_sponsorship("Visa sponsorship is available for qualified candidates") == VisaSponsorshipStatus.AVAILABLE.value
        assert extract_visa_sponsorship("Must be US Citizen or Green Card holder") == VisaSponsorshipStatus.CITIZEN_OR_PR_ONLY.value
        assert extract_visa_sponsorship("No sponsorship provided for this role") == VisaSponsorshipStatus.NOT_AVAILABLE.value
        assert extract_visa_sponsorship("Standard requirements without visa text") == VisaSponsorshipStatus.UNKNOWN.value


# -----------------------------------------------------------------------------
# 3. Alert Priority Logic Tests
# -----------------------------------------------------------------------------
class TestAlertPriority:
    def test_p0_priority_fresh_and_strong_match(self):
        p = calculate_alert_priority(
            match_score=85.0,
            is_eligible=True,
            freshness=FreshnessStatus.FRESH_0_6_HOURS,
            role_category="design_verification",
        )
        assert p == AlertPriority.P0

    def test_p1_priority_fresh_and_reasonable_match(self):
        p = calculate_alert_priority(
            match_score=68.0,
            is_eligible=True,
            freshness=FreshnessStatus.FRESH_6_24_HOURS,
            role_category="design_verification",
        )
        assert p == AlertPriority.P1

    def test_p2_priority_recent_and_strong_match(self):
        p = calculate_alert_priority(
            match_score=85.0,
            is_eligible=True,
            freshness=FreshnessStatus.RECENT_1_3_DAYS,
            role_category="design_verification",
        )
        assert p == AlertPriority.P2

    def test_p3_priority_older_or_low_match(self):
        p = calculate_alert_priority(
            match_score=50.0,
            is_eligible=True,
            freshness=FreshnessStatus.OLDER,
            role_category="design_verification",
        )
        assert p == AlertPriority.P3

    def test_unknown_priority_when_ineligible_or_unknown_freshness(self):
        p = calculate_alert_priority(
            match_score=40.0,
            is_eligible=False,
            freshness=FreshnessStatus.UNKNOWN,
            role_category="unknown",
        )
        assert p == AlertPriority.UNKNOWN


# -----------------------------------------------------------------------------
# 4. Source Adapter & Failure Isolation Tests
# -----------------------------------------------------------------------------
class FailingSourceAdapter(JobSourceAdapter):
    @property
    def adapter_name(self) -> str:
        return "failing_unstable_source"

    @property
    def source_category(self) -> str:
        return "careers_portal"

    def supports_region(self, region: str) -> bool:
        return True

    def supports_freshness(self) -> bool:
        return True

    def health_status(self) -> str:
        return "unhealthy"

    def fetch_jobs(self, query: JobDiscoveryQuery) -> list[RawJobPayload]:
        raise ConnectionResetError("Remote career portal connection reset by peer")



class TestSourceIsolationAndMonitoringService:
    def test_adapter_failure_isolation_does_not_crash_cycle(self, in_memory_db, candidate_context):
        profile, fact_bank = candidate_context

        # Register one failing adapter and one working mock adapter
        working_adapter = MockJobSourceAdapter()
        failing_adapter = FailingSourceAdapter()

        service = FreshJobMonitoringService(
            conn=in_memory_db,
            profile=profile,
            fact_bank=fact_bank,
            adapters=[working_adapter, failing_adapter],
        )

        report = service.run_monitoring_cycle(region="all", dry_run=False)

        assert report.sources_checked == 2
        assert report.sources_successful == 1
        assert report.sources_failed == 1
        assert report.source_health["failing_unstable_source"]["status"] == "failed"
        assert "connection reset" in report.source_health["failing_unstable_source"]["error"].lower()
        assert report.total_jobs_found > 0

        # Verify audit records written to DB
        repo = JobRepository(in_memory_db)
        runs = repo.list_source_runs()
        assert len(runs) == 2
        failed_run = next(r for r in runs if r.source_name == "failing_unstable_source")
        assert failed_run.status == "failed"

    def test_cross_source_deduplication(self, in_memory_db, candidate_context):
        profile, fact_bank = candidate_context

        # Create two adapters returning the same canonical job
        now = datetime.now(UTC).isoformat()
        payload_a = RawJobPayload(
            source="source_portal_a",
            source_url="https://portal-a.com/job/101",
            company="Texas Instruments India",
            title="Design Verification Engineer",
            location="Bengaluru",
            country="India",
            raw_payload="SystemVerilog UVM AXI4 verification role.",
            discovered_at=now,
            content_hash="hash_portal_a_101",
            metadata={"published_at": now},
        )
        payload_b = RawJobPayload(
            source="source_portal_b",
            source_url="https://portal-b.com/job/999",
            company="Texas Instruments India",
            title="Design Verification Engineer",
            location="Bengaluru",
            country="India",
            raw_payload="SystemVerilog UVM AXI4 verification role.",
            discovered_at=now,
            content_hash="hash_portal_b_999",
            metadata={"published_at": now},
        )

        adapter_a = MockJobSourceAdapter(custom_payloads=[payload_a])
        adapter_b = MockJobSourceAdapter(custom_payloads=[payload_b])

        service = FreshJobMonitoringService(
            conn=in_memory_db,
            profile=profile,
            fact_bank=fact_bank,
            adapters=[adapter_a, adapter_b],
        )

        report = service.run_monitoring_cycle(region="all", dry_run=False)
        assert report.total_jobs_found == 2
        assert report.unique_jobs_ingested == 1  # Deduplicated into 1 canonical job

        repo = JobRepository(in_memory_db)
        norm_jobs = repo.list_normalized_jobs()
        assert len(norm_jobs) == 1
        assert "source_portal_a" in norm_jobs[0].source_references
        assert "source_portal_b" in norm_jobs[0].source_references

    def test_alert_deduplication_prevents_spam_notifications(self, in_memory_db, candidate_context):
        profile, fact_bank = candidate_context
        adapter = MockJobSourceAdapter()

        service = FreshJobMonitoringService(
            conn=in_memory_db,
            profile=profile,
            fact_bank=fact_bank,
            adapters=[adapter],
        )

        # First cycle generates notifications for P0/P1 jobs
        report1 = service.run_monitoring_cycle(region="all", dry_run=False)
        initial_notifs = report1.notifications_generated
        assert initial_notifs > 0

        # Second identical cycle must NOT duplicate notifications
        report2 = service.run_monitoring_cycle(region="all", dry_run=False)
        assert report2.notifications_generated == 0

    def test_human_gated_proposals_status_is_proposed_never_auto_applied(self, in_memory_db, candidate_context):
        profile, fact_bank = candidate_context
        adapter = MockJobSourceAdapter()

        service = FreshJobMonitoringService(
            conn=in_memory_db,
            profile=profile,
            fact_bank=fact_bank,
            adapters=[adapter],
        )

        report = service.run_monitoring_cycle(region="all", dry_run=False)
        assert report.notifications_generated > 0

        notif_service = ScheduleNotificationService(in_memory_db)
        proposals = notif_service.list_proposals(status=NotificationDispatchStatus.PROPOSED)
        assert len(proposals) >= report.notifications_generated

        for p in proposals:
            assert p.status == NotificationDispatchStatus.PROPOSED
            assert "Human Action: Review in Fresh Jobs dashboard" in p.body_content

        # Confirm applications are NOT auto-applied
        repo = JobRepository(in_memory_db)
        apps = repo.list_applications()

        for app in apps:
            assert app.status.value != "applied"

    def test_dry_run_mode_has_zero_side_effects(self, in_memory_db, candidate_context):
        profile, fact_bank = candidate_context
        adapter = MockJobSourceAdapter()

        service = FreshJobMonitoringService(
            conn=in_memory_db,
            profile=profile,
            fact_bank=fact_bank,
            adapters=[adapter],
        )

        report = service.run_monitoring_cycle(region="all", dry_run=True)
        assert report.dry_run is True
        assert report.total_jobs_found > 0
        assert len(report.alerts) > 0

        # Verify DB is completely untouched
        repo = JobRepository(in_memory_db)
        assert len(repo.list_normalized_jobs()) == 0
        assert len(repo.list_source_runs()) == 0
        assert len(repo.list_job_alerts()) == 0

        notif_service = ScheduleNotificationService(in_memory_db)
        assert len(notif_service.list_proposals()) == 0


# -----------------------------------------------------------------------------
# 5. Database Schema Migration & Repository Tests
# -----------------------------------------------------------------------------
class TestDatabasePersistenceAndMigration:
    def test_create_tables_idempotency(self, in_memory_db):
        # Calling create_tables multiple times must not fail
        create_tables(in_memory_db)
        create_tables(in_memory_db)

    def test_job_alerts_and_source_runs_crud(self, in_memory_db):
        repo = JobRepository(in_memory_db)

        # 1. Source Run
        run = JobSourceRunRecord(
            source_name="qualcomm_careers",
            run_timestamp=datetime.now(UTC).isoformat(),
            status="success",
            jobs_discovered=5,
            jobs_accepted=5,
            jobs_rejected=0,
            fresh_jobs_count=3,
            duration_ms=120.5,
        )
        run_id = repo.record_source_run(run)
        assert run_id > 0

        runs = repo.list_source_runs(source_name="qualcomm_careers")
        assert len(runs) == 1
        assert runs[0].fresh_jobs_count == 3

        # 2. Normalized Job
        norm = normalize_job_listing(
            company="NVIDIA India",
            title="ASIC Verification Engineer",
            raw_text="SystemVerilog UVM testbenches in Bengaluru.",
            location="Bengaluru",
            country="India",
            published_at=datetime.now(UTC).isoformat(),
        )
        job_id = repo.insert_normalized_job(norm)

        # 3. Job Alert
        alert = JobAlertRecord(
            job_id=job_id,
            company=norm.company,
            title=norm.title,
            location=norm.location,
            country=norm.country,
            published_at=norm.published_at,
            freshness_status=FreshnessStatus.FRESH_0_6_HOURS,
            freshness_age_hours=2.5,
            match_score=88.5,
            priority=AlertPriority.P0,
            status="proposed",
            created_at=datetime.now(UTC).isoformat(),
        )
        alert_id = repo.create_job_alert(alert)
        assert alert_id > 0

        fetched_alert = repo.get_job_alert_by_job_id(job_id)
        assert fetched_alert is not None
        assert fetched_alert.priority == AlertPriority.P0
        assert fetched_alert.match_score == 88.5

        # 4. List Fresh Jobs Query
        fresh_jobs = repo.list_fresh_jobs(max_age_hours=24.0)
        assert len(fresh_jobs) == 1
        assert fresh_jobs[0].company == "NVIDIA India"


# -----------------------------------------------------------------------------
# 6. CLI Entrypoint Tests
# -----------------------------------------------------------------------------
class TestCLIEntrypoint:
    def test_cli_dry_run_execution(self, monkeypatch, tmp_path):
        test_db = str(tmp_path / "test_cli.db")
        monkeypatch.setattr(
            "sys.argv",
            ["job-ai-monitor", "--region", "india", "--dry-run", "--limit", "5", "--db-path", test_db],
        )
        exit_code = cli_main()
        assert exit_code == 0

    def test_cli_live_run_execution(self, monkeypatch, tmp_path):
        test_db = str(tmp_path / "test_cli_live.db")
        monkeypatch.setattr(
            "sys.argv",
            ["job-ai-monitor", "--region", "all", "--fresh-only", "--limit", "5", "--db-path", test_db],
        )
        exit_code = cli_main()
        assert exit_code == 0
