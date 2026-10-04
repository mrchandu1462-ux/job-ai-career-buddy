"""Comprehensive test suite for Fresh Job Intelligence, 24-Hour Tracking, 8D Ranking, and Notification Engine."""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import (
    FreshnessBucket,
    FreshnessConfidence,
    FreshnessStatus,
    JobPriorityCategory,
    NormalizedJob,
    VisaSponsorshipCategory,
)
from app.db.repository import DuplicateFingerprintError, JobRepository
from app.db.schema import create_schema
from app.jobs.digest import DailyJobDigestService
from app.jobs.freshness import (
    calculate_fresh_job_priority_score,
    calculate_granular_freshness,
    calculate_job_freshness,
    classify_geography,
    classify_visa_sponsorship_category,
    extract_workplace_type,
)
from app.jobs.normalizer import generate_job_fingerprint
from app.jobs.scanner import FreshJobScanner
from app.jobs.sources.adapters import JobSourceAdapter
from app.jobs.sources.base import JobDiscoveryQuery, RawJobPayload
from app.jobs.watchlist import CompanyWatchlistService
from app.profile.loader import load_candidate_profile, load_fact_bank


@pytest.fixture
def memory_conn():
    """In-memory SQLite connection with complete initialized schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    yield conn
    conn.close()


# -----------------------------------------------------------------------------
# 1. Granular Freshness & Timezone Tests
# -----------------------------------------------------------------------------
def test_fresh_le_1h_job():
    now = datetime.now(UTC)
    pub_30m_ago = (now - timedelta(minutes=30)).isoformat()

    bucket, age, conf, src = calculate_granular_freshness(pub_30m_ago, now=now)
    assert bucket == FreshnessBucket.LE_1_HOUR
    assert age is not None and age <= 1.0
    assert conf == FreshnessConfidence.HIGH
    assert src == "official_listing"


def test_fresh_le_24h_job():
    now = datetime.now(UTC)
    pub_18h_ago = (now - timedelta(hours=18)).isoformat()

    bucket, age, conf, _ = calculate_granular_freshness(pub_18h_ago, now=now)
    assert bucket == FreshnessBucket.LE_24_HOURS
    assert age is not None and 12.0 < age <= 24.0
    assert conf == FreshnessConfidence.HIGH


def test_stale_job_25h_classified_days_1_3():
    now = datetime.now(UTC)
    pub_25h_ago = (now - timedelta(hours=25)).isoformat()

    bucket, age, _, _ = calculate_granular_freshness(pub_25h_ago, now=now)
    assert bucket == FreshnessBucket.DAYS_1_3
    assert age is not None and 24.0 < age <= 72.0


def test_older_than_7_days_job():
    now = datetime.now(UTC)
    pub_10d_ago = (now - timedelta(days=10)).isoformat()

    bucket, age, _, _ = calculate_granular_freshness(pub_10d_ago, now=now)
    assert bucket == FreshnessBucket.OLDER_7_DAYS
    assert age is not None and age > 168.0


def test_unknown_and_vague_timestamp_zero_fabrication():
    """Zero-fabrication rule: Vague words like 'recently' or missing dates must NOT be assumed fresh <=24h."""
    now = datetime.now(UTC)

    bucket1, age1, conf1, _ = calculate_granular_freshness(None, now=now)
    assert bucket1 == FreshnessBucket.UNKNOWN
    assert age1 is None
    assert conf1 == FreshnessConfidence.LOW

    bucket2, age2, conf2, _ = calculate_granular_freshness("Just posted today recently", now=now)
    assert bucket2 == FreshnessBucket.UNKNOWN
    assert age2 is None
    assert conf2 == FreshnessConfidence.LOW


def test_date_only_format_handled_conservatively():
    """Date-only format (e.g. 2026-10-04) parsed conservatively with MEDIUM confidence."""
    now = datetime(2026, 10, 4, 18, 0, 0, tzinfo=UTC)
    _, age, conf, src = calculate_granular_freshness("2026-10-04", now=now)
    assert age is not None
    assert conf == FreshnessConfidence.MEDIUM
    assert src in ("official_listing", "date_only_listing")


def test_backward_compatible_calculate_job_freshness():
    now = datetime.now(UTC)
    pub_2h_ago = (now - timedelta(hours=2)).isoformat()
    status, age, conf = calculate_job_freshness(pub_2h_ago, now=now)
    assert status == FreshnessStatus.FRESH_0_6_HOURS
    assert age is not None and age <= 6.0
    assert conf == 1.0


# -----------------------------------------------------------------------------
# 2. International Visa Sponsorship Categorization Tests
# -----------------------------------------------------------------------------
def test_sponsorship_confirmed():
    text = "We offer full visa sponsorship and global relocation assistance for this role."
    cat, conf = classify_visa_sponsorship_category(text)
    assert cat == VisaSponsorshipCategory.SPONSORSHIP_CONFIRMED
    assert conf == FreshnessConfidence.HIGH


def test_sponsorship_not_supported():
    text1 = "No visa sponsorship available. Must be authorized to work without sponsorship."
    cat1, conf1 = classify_visa_sponsorship_category(text1)
    assert cat1 == VisaSponsorshipCategory.SPONSORSHIP_NOT_SUPPORTED
    assert conf1 == FreshnessConfidence.HIGH

    text2 = "US Citizen or Permanent Resident (Green Card) required."
    cat2, _ = classify_visa_sponsorship_category(text2)
    assert cat2 == VisaSponsorshipCategory.SPONSORSHIP_NOT_SUPPORTED


def test_sponsorship_possible():
    text = "International applicants welcome; relocation assistance provided."
    cat, conf = classify_visa_sponsorship_category(text)
    assert cat == VisaSponsorshipCategory.SPONSORSHIP_POSSIBLE
    assert conf == FreshnessConfidence.MEDIUM


def test_sponsorship_unknown_never_assumed():
    text = "Design verification engineer responsible for UVM testbench development."
    cat, conf = classify_visa_sponsorship_category(text)
    assert cat == VisaSponsorshipCategory.SPONSORSHIP_UNKNOWN
    assert conf == FreshnessConfidence.LOW


# -----------------------------------------------------------------------------
# 3. Geography & Workplace Extraction Tests
# -----------------------------------------------------------------------------
def test_geography_india_priority_hubs():
    geo1 = classify_geography("Bengaluru, Karnataka", "India")
    assert geo1["is_india"] is True
    assert geo1["priority_hub"] == "Bengaluru"

    geo2 = classify_geography("Hyderabad, Telangana", "India")
    assert geo2["is_india"] is True
    assert geo2["priority_hub"] == "Hyderabad"


def test_geography_overseas_markets():
    geo_us = classify_geography("Austin, Texas", "United States")
    assert geo_us["is_india"] is False
    assert geo_us["is_overseas"] is True

    geo_de = classify_geography("Munich", "Germany")
    assert geo_de["is_india"] is False
    assert geo_de["is_overseas"] is True


def test_workplace_type_extraction():
    assert extract_workplace_type("100% remote work from home") == "remote"
    assert extract_workplace_type("Hybrid work arrangement 3 days in office") == "hybrid"
    assert extract_workplace_type("On-site position at Bengaluru facility") == "onsite"
    assert extract_workplace_type("Standard engineering role") == "unknown"


# -----------------------------------------------------------------------------
# 4. Explainable 8-Dimensional Priority Score Tests
# -----------------------------------------------------------------------------
def test_critical_match_fresh_score():
    score = calculate_fresh_job_priority_score(
        match_score=92.0,
        freshness_bucket=FreshnessBucket.LE_1_HOUR,
        freshness_confidence=FreshnessConfidence.HIGH,
        role_score=90.0,
        project_score=85.0,
        fresher_fit=True,
        is_watchlist=True,
        has_direct_url=True,
        is_india=True,
    )
    assert score.freshness == 25.0
    assert score.technical_match == 23.0
    assert score.total_score >= 88.0
    assert score.category == JobPriorityCategory.CRITICAL
    assert score.is_fresh_24h_match is True


def test_stale_job_low_freshness_score():
    score = calculate_fresh_job_priority_score(
        match_score=80.0,
        freshness_bucket=FreshnessBucket.OLDER_7_DAYS,
        freshness_confidence=FreshnessConfidence.HIGH,
        fresher_fit=True,
    )
    assert score.freshness == 0.0
    assert score.category == JobPriorityCategory.EXPIRED_STALE
    assert score.is_fresh_24h_match is False


# -----------------------------------------------------------------------------
# 5. Database Repository & Deduplication Tests
# -----------------------------------------------------------------------------
def test_insert_and_retrieve_normalized_job(memory_conn):
    repo = JobRepository(memory_conn)
    now_iso = datetime.now(UTC).isoformat()

    job = NormalizedJob(
        company="NVIDIA",
        title="ASIC Verification Engineer",
        location="Bengaluru, India",
        country="India",
        employment_type="Full-time",
        experience_min=0.0,
        experience_max=2.0,
        description="Design verification with SystemVerilog and UVM.",
        requirements="UVM, SystemVerilog",
        skills=["SystemVerilog", "UVM", "SVA"],
        application_url="https://nvidia.com/careers/123",
        source="career_page",
        first_seen=now_iso,
        last_seen=now_iso,
        fingerprint=generate_job_fingerprint("NVIDIA", "ASIC Verification Engineer", "Bengaluru", now_iso),
        published_at=now_iso,
        freshness_bucket="<= 1 hour",
        freshness_confidence="HIGH",
        freshness_age_hours=0.5,
        region="india",
        city="Bengaluru",
        priority_score=94.0,
        priority_category="CRITICAL",
        is_watchlist=True,
    )

    job_id = repo.insert_normalized_job(job)
    assert job_id > 0

    retrieved = repo.get_normalized_job(job_id)
    assert retrieved is not None
    assert retrieved.company == "NVIDIA"
    assert retrieved.freshness_bucket == "<= 1 hour"
    assert retrieved.priority_score == 94.0
    assert retrieved.is_watchlist is True


def test_duplicate_fingerprint_prevention(memory_conn):
    repo = JobRepository(memory_conn)
    now_iso = datetime.now(UTC).isoformat()
    fp = "nvidia_asic_verification_unique_123"

    job1 = NormalizedJob(
        company="NVIDIA",
        title="ASIC Verification",
        location="Bengaluru",
        source="career_portal",
        first_seen=now_iso,
        last_seen=now_iso,
        fingerprint=fp,
    )
    repo.insert_normalized_job(job1)

    # Second insert with identical fingerprint must raise DuplicateFingerprintError
    job2 = NormalizedJob(
        company="NVIDIA",
        title="ASIC Verification",
        location="Bengaluru",
        source="rss_feed",
        first_seen=now_iso,
        last_seen=now_iso,
        fingerprint=fp,
    )
    with pytest.raises(DuplicateFingerprintError):
        repo.insert_normalized_job(job2)


# -----------------------------------------------------------------------------
# 6. Company Watchlist Service Tests
# -----------------------------------------------------------------------------
def test_company_watchlist_crud(memory_conn):
    watchlist_service = CompanyWatchlistService(memory_conn)

    # Initial default seeded
    initial = watchlist_service.list_watchlist()
    assert len(initial) >= 15
    assert watchlist_service.is_watched("NVIDIA") is True
    assert watchlist_service.is_watched("Qualcomm") is True

    # Add custom company
    watchlist_service.add_company("Tenstorrent", priority_level="CRITICAL", notes="RISC-V AI hardware")
    assert watchlist_service.is_watched("Tenstorrent") is True

    # Remove company
    removed = watchlist_service.remove_company("Tenstorrent")
    assert removed is True
    assert watchlist_service.is_watched("Tenstorrent") is False


# -----------------------------------------------------------------------------
# 7. Daily Job Digest Service Tests
# -----------------------------------------------------------------------------
def test_daily_digest_generation(memory_conn):
    repo = JobRepository(memory_conn)
    digest_service = DailyJobDigestService(memory_conn)
    now_iso = datetime.now(UTC).isoformat()

    # Insert mock fresh jobs
    job_in = NormalizedJob(
        company="Qualcomm India",
        title="Design Verification Engineer",
        location="Bengaluru, India",
        country="India",
        source="careers",
        first_seen=now_iso,
        last_seen=now_iso,
        fingerprint="fp_qc_india_1",
        published_at=now_iso,
        freshness_age_hours=2.0,
        region="india",
        priority_score=92.0,
        priority_category="CRITICAL",
        is_watchlist=True,
    )
    repo.insert_normalized_job(job_in)

    job_us = NormalizedJob(
        company="AMD",
        title="DV Engineer",
        location="Austin, TX",
        country="United States",
        source="careers",
        first_seen=now_iso,
        last_seen=now_iso,
        fingerprint="fp_amd_us_1",
        published_at=now_iso,
        freshness_age_hours=5.0,
        region="overseas",
        priority_score=85.0,
        priority_category="HIGH",
        is_watchlist=True,
    )
    repo.insert_normalized_job(job_us)

    data = digest_service.generate_digest_data(hours=24.0)
    assert data["total_fresh"] >= 2
    assert data["india_fresh_count"] >= 1
    assert data["overseas_fresh_count"] >= 1

    md_report = digest_service.generate_markdown_digest(hours=24.0)
    assert "JOB-AI DAILY FRESH JOB DIGEST" in md_report
    assert "INDIA FRESH JOBS" in md_report
    assert "OVERSEAS FRESH JOBS" in md_report
    assert "Zero-Fabrication Policy" in md_report


# -----------------------------------------------------------------------------
# 8. Fresh Job Scanner & Source Failure Isolation Tests
# -----------------------------------------------------------------------------
class MockDegradedAdapter(JobSourceAdapter):
    """Adapter that simulates network failure to verify scanner resilience."""

    @property
    def adapter_name(self) -> str:
        return "mock_failing_portal"

    @property
    def source_category(self) -> str:
        return "career_pages"

    def supports_region(self, region: str) -> bool:
        return True

    def supports_freshness(self) -> bool:
        return True

    def fetch_jobs(self, query: JobDiscoveryQuery) -> list[RawJobPayload]:
        raise ConnectionError("Simulated portal timeout / rate-limit")


def test_scanner_with_source_failure_isolation(memory_conn):
    """A failing source must NOT crash the scanner cycle."""
    profile = load_candidate_profile()
    facts = load_fact_bank()

    scanner = FreshJobScanner(conn=memory_conn, profile=profile, fact_bank=facts, allow_mock=True)
    scanner.register_adapter(MockDegradedAdapter())

    report = scanner.scan(region="all", hours=24.0, dry_run=False)
    assert report.sources_total >= 2
    assert report.sources_successful >= 1
    assert report.sources_failed >= 1
    assert report.jobs_discovered > 0
    assert report.fresh_24h > 0


def test_scanner_dry_run_mode(memory_conn):
    """Dry run scan must not persist new rows in database."""
    repo = JobRepository(memory_conn)
    initial_count = repo.count_normalized_jobs()

    scanner = FreshJobScanner(conn=memory_conn, allow_mock=True)
    report = scanner.scan(region="all", hours=24.0, dry_run=True)

    assert report.jobs_discovered > 0
    # Count in DB must remain unchanged
    after_count = repo.count_normalized_jobs()
    assert after_count == initial_count


def test_notification_proposal_human_gated_safety(memory_conn):
    """Notifications are proposed for review and never auto-submitted."""
    scanner = FreshJobScanner(conn=memory_conn, allow_mock=True)
    report = scanner.scan(region="all", hours=24.0, dry_run=False)
    assert report.jobs_discovered > 0

    repo = JobRepository(memory_conn)
    alerts = repo.list_job_alerts()
    for alert in alerts:
        # Proposed state requires explicit human approval
        assert alert.status == "proposed"
        assert alert.notification_count >= 1

    # Running scan again should not duplicate proposed notifications
    second_report = scanner.scan(region="all", hours=24.0, dry_run=False)
    assert second_report.notifications_proposed == 0  # Deduplicated!
