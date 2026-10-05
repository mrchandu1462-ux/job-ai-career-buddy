"""Tests for Phase 5 Job Discovery Sources, Active Status Verification, and Deduplication."""

import pytest

from app.db.connection import get_db
from app.db.models import JobStatus
from app.db.repository import JobRepository
from app.jobs.classifier import RoleCategory, RoleClassifier
from app.jobs.normalizer import normalize_job_listing
from app.jobs.sources.base import (
    ActiveVerificationResult,
    JobActiveStatus,
    JobDiscoveryQuery,
    RawJobPayload,
)
from app.jobs.sources.career_pages import CompanyCareerSource
from app.jobs.sources.job_board import StructuredJobBoardSource
from app.jobs.sources.manual import ManualJobSource
from app.jobs.sources.registry import JobSourceRegistry
from app.jobs.verifier import ActiveStatusVerifier, sync_job_status_from_verification


@pytest.fixture
def db_conn():
    with get_db(":memory:") as conn:
        yield conn


@pytest.fixture
def job_repo(db_conn):
    return JobRepository(db_conn)


def test_job_source_abstraction_and_registry():
    """Test registering multiple sources, querying across sources, and fetching by identifier."""
    registry = JobSourceRegistry()
    manual_src = ManualJobSource()
    career_src = CompanyCareerSource("nvidia")
    board_src = StructuredJobBoardSource("linkedin")

    registry.register_source(manual_src)
    registry.register_source(career_src)
    registry.register_source(board_src)

    assert len(registry.list_sources()) == 3
    assert "manual" in registry.list_sources()
    assert "careers_nvidia" in registry.list_sources()
    assert "board_linkedin" in registry.list_sources()

    # Ingest manual job
    manual_payload = manual_src.submit_manual_job(
        company="NVIDIA India",
        title="ASIC Verification Engineer",
        raw_text="SystemVerilog, UVM, and SVA in Bengaluru. 2025 batch passouts.",
        location="Bengaluru",
        source_url="https://nvidia.wd5.myworkdayjobs.com/job1",
    )
    assert manual_payload.content_hash is not None

    # Ingest career portal postings
    career_src.load_structured_postings([
        {
            "company": "NVIDIA India",
            "title": "Verification Intern",
            "description": "6-month internship in Bengaluru. UVM and SV testbenches.",
            "location": "Bengaluru",
            "url": "https://nvidia.com/careers/intern1",
        }
    ])

    # Search across all sources
    query = JobDiscoveryQuery(keywords=["Verification"], locations=["Bengaluru"])
    results = registry.search_all(query)
    assert len(results) == 2
    assert any(r.title == "ASIC Verification Engineer" for r in results)
    assert any(r.title == "Verification Intern" for r in results)

    # Fetch specific job by identifier
    fetched = manual_src.fetch_job(manual_payload.content_hash)
    assert fetched is not None
    assert fetched.company == "NVIDIA India"


def test_active_status_verification():
    """Test verifying active, expired, archived, and unknown listing statuses with explainable reasons."""
    verifier = ActiveStatusVerifier(stale_threshold_days=30)

    # 1. Active listing on official portal
    active_payload = RawJobPayload(
        company="Qualcomm India",
        title="Design Verification Engineer",
        raw_payload="Active listing for DV Engineer in Hyderabad. SystemVerilog, UVM.",
        location="Hyderabad",
        country="India",
        source="careers_qualcomm",
        source_url="https://qualcomm.wd5.myworkdayjobs.com/job123",
        application_url="https://qualcomm.wd5.myworkdayjobs.com/job123/apply",
        discovered_at="2026-10-01T10:00:00+00:00",
        content_hash="hash123",
    )
    res_active: ActiveVerificationResult = verifier.verify(active_payload)
    assert res_active.status == JobActiveStatus.ACTIVE
    assert res_active.is_active is True
    assert "official company careers portal" in res_active.reason

    # 2. Expired listing with explicit closed language
    expired_payload = RawJobPayload(
        company="Qualcomm India",
        title="Design Verification Engineer",
        raw_payload="This position is closed. Applications are closed.",
        location="Hyderabad",
        country="India",
        source="careers_qualcomm",
        discovered_at="2026-10-01T10:00:00+00:00",
        content_hash="hash_closed",
    )
    res_expired = verifier.verify(expired_payload)
    assert res_expired.status == JobActiveStatus.EXPIRED
    assert res_expired.is_active is False
    assert "explicit language" in res_expired.reason

    # 3. Expired listing from portal status signal
    res_portal_closed = verifier.verify(active_payload, portal_status="closed")
    assert res_portal_closed.status == JobActiveStatus.EXPIRED
    assert res_portal_closed.is_active is False

    # 4. Unreachable URL (404/410)
    res_unreachable = verifier.verify(active_payload, is_url_reachable=False)
    assert res_unreachable.status == JobActiveStatus.EXPIRED
    assert res_unreachable.is_active is False
    assert "unreachable" in res_unreachable.reason

    # 5. Archived due to stale age (>30 days)
    stale_payload = RawJobPayload(
        company="OldCo",
        title="DV Trainee",
        raw_payload="Old posting without application url.",
        location="Pune",
        source="external_scrape",
        discovered_at="2026-05-01T10:00:00+00:00",
        content_hash="stale_hash",
    )
    res_stale = verifier.verify(stale_payload)
    assert res_stale.status == JobActiveStatus.ARCHIVED
    assert res_stale.is_active is False

    # 6. Status sync helper
    norm_job = normalize_job_listing(company="Intel", title="DV Engineer", raw_text="SV UVM in Bengaluru.")
    assert sync_job_status_from_verification(norm_job, res_active) == JobStatus.ACTIVE
    assert sync_job_status_from_verification(norm_job, res_expired) == JobStatus.EXPIRED


def test_role_classifier_semiconductor_categories():
    """Test RoleClassifier mapping job titles to semiconductor categories with explainable score and justification."""
    classifier = RoleClassifier()

    # Core Design Verification
    res_dv = classifier.classify("Design Verification Engineer", "SystemVerilog testbenches")
    assert res_dv.category == RoleCategory.DESIGN_VERIFICATION
    assert res_dv.relevance_score == 20.0

    # ASIC Verification
    res_asic = classifier.classify("ASIC Verification Engineer", "UVM verification of complex IP")
    assert res_asic.category == RoleCategory.ASIC_VERIFICATION
    assert res_asic.relevance_score == 20.0

    # SoC Verification
    res_soc = classifier.classify("SoC Verification Engineer", "Full chip simulation")
    assert res_soc.category == RoleCategory.SOC_VERIFICATION
    assert res_soc.relevance_score == 20.0

    # Functional Verification
    res_fv = classifier.classify("Functional Verification Engineer", "Constrained random tests")
    assert res_fv.category == RoleCategory.FUNCTIONAL_VERIFICATION
    assert res_fv.relevance_score == 20.0

    # Verification Intern
    res_intern = classifier.classify("Verification Intern", "6 months college internship")
    assert res_intern.category == RoleCategory.VERIFICATION_INTERN
    assert res_intern.relevance_score == 19.0

    # Graduate Engineer Trainee
    res_get = classifier.classify("Graduate Engineer Trainee - VLSI", "Entry level campus hiring")
    assert res_get.category == RoleCategory.GRADUATE_ENGINEER_TRAINEE
    assert res_get.relevance_score == 18.0

    # RTL Design
    res_rtl = classifier.classify("RTL Design Engineer", "Verilog and digital logic synthesis")
    assert res_rtl.category == RoleCategory.RTL_DESIGN
    assert res_rtl.relevance_score == 16.0

    # Non-semiconductor Role
    res_other = classifier.classify("DevOps Cloud Engineer", "Kubernetes and AWS terraform")
    assert res_other.category == RoleCategory.OTHER
    assert res_other.relevance_score <= 5.0
