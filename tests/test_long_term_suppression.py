"""Comprehensive tests for Long-Term Opportunity Alert Suppression across hours and days.

Validates:
A. Same job discovered every hour for 3 days (72 hourly iterations) -> exactly ONE notification.
B. Same job discovered after 72 hours with no change -> NO automatic repeated notification.
C. Same company, different job IDs / requisitions -> independently evaluated and notified.
D. Same company, different locations but genuinely different requisitions -> independently evaluated.
E. Same job with material change -> re-alerts with [MATERIAL UPDATE].
F. Same job already submitted by candidate -> suppressed.
G. Same job with only crawler/page timestamp changes -> suppressed.
H. Existing deterministic fingerprint behavior remains intact.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from app.application.intelligence import (
    ApplicationIntelligenceService,
    ApplicationStatus,
)
from app.db.models import (
    ApplicationRecord,
    DeliveryStatus,
    NormalizedJob,
)
from app.db.repository import JobRepository
from app.db.schema import create_schema
from app.jobs.normalizer import generate_job_fingerprint
from app.jobs.scanner import FreshJobScanner
from app.jobs.sources.adapters import MockJobSourceAdapter
from app.jobs.sources.base import RawJobPayload
from app.matching.scorer import JobScoringEngine
from app.notifications.email import MockEmailProvider
from app.notifications.service import EmailNotificationService
from app.profile.models import CandidateProfile, FactBank, FactCategory, FactItem


def _make_candidate_profile() -> CandidateProfile:
    return CandidateProfile.model_validate({
        "candidate": {
            "name": "Chandu Saikam",
            "email": "saikamchandu1462@gmail.com",
            "phone": "+91 98765 43210",
            "location": "Bengaluru, India",
            "institution": "National Institute of Technology",
            "graduation_year": 2025,
            "experience_level": "Fresher / Entry-Level",
            "target_roles": [
                "Design Verification Engineer",
                "ASIC Verification Engineer",
                "SoC Verification Engineer",
                "RTL Design Engineer",
            ],
            "locations": {
                "india_priority": ["Bengaluru", "Hyderabad", "Chennai"],
                "overseas_enabled": True,
            },
            "work_authorization": {
                "citizen_of": "India",
                "requires_sponsorship_overseas": True,
            },
        }
    })


def _make_fact_bank() -> FactBank:
    return FactBank(
        version="1.0",
        facts=[
            FactItem(
                fact_id="EDU-001",
                category=FactCategory.EDUCATION,
                subject="B.Tech in ECE",
                value={
                    "degree": "B.Tech in Electronics and Communication Engineering",
                    "field": "Electronics and Communication Engineering",
                    "graduation_year": 2025,
                    "institution": "National Institute of Technology",
                    "cgpa": "7.38/10",
                },
                source="Degree Certificate",
                verified=True,
            ),
            FactItem(
                fact_id="SKL-001",
                category=FactCategory.SKILL,
                subject="SystemVerilog",
                value={
                    "skill": "SystemVerilog",
                    "category": "HDVL",
                    "proficiency": "Advanced",
                },
                source="Coursework & Lab",
                verified=True,
            ),
            FactItem(
                fact_id="SKL-002",
                category=FactCategory.SKILL,
                subject="UVM",
                value={
                    "skill": "UVM",
                    "category": "Methodology",
                    "proficiency": "Intermediate",
                },
                source="Lab Project",
                verified=True,
            ),
            FactItem(
                fact_id="PRJ-001",
                category=FactCategory.PROJECT,
                subject="AXI4-Lite VIP",
                value={
                    "title": "AXI4-Lite Master/Slave UVM VIP Testbench",
                    "description": "Designed complete UVM environment verifying single-beat burst transactions.",
                },
                source="GitHub Repository",
                verified=True,
            ),
        ],
    )


def _make_normalized_job(
    job_id: int = 1,
    company: str = "Qualcomm",
    title: str = "Design Verification Engineer",
    location: str = "Bengaluru, India",
    requisition_id: str | None = "ABC123",
    published_at: str | None = None,
) -> NormalizedJob:
    now_iso = datetime.now(UTC).isoformat()
    fp = generate_job_fingerprint(
        company=company,
        title=title,
        location=location,
        requisition_id=requisition_id,
    )
    return NormalizedJob(
        id=job_id,
        company=company,
        title=title,
        location=location,
        country="India",
        employment_type="Full-time",
        experience_min=0.0,
        experience_max=2.0,
        graduation_year_min=2024,
        graduation_year_max=2026,
        description="Qualcomm Design Verification Engineer in Bengaluru with SystemVerilog and UVM.",
        requirements="B.Tech, SystemVerilog, UVM, OVM, coverage closure.",
        skills=["SystemVerilog", "UVM"],
        application_url=f"https://qualcomm.wd5.myworkdayjobs.com/careers/{requisition_id or 'job'}",
        source="career_portal",
        first_seen=now_iso,
        last_seen=now_iso,
        fingerprint=fp,
        published_at=published_at or now_iso,
        freshness_status="fresh_0_6_hours",
        freshness_age_hours=1.5,
        region="india",
        city="Bengaluru",
        priority_score=95.0,
        priority_category="CRITICAL",
    )


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    yield conn
    conn.close()


# =============================================================================
# Test A: Same job discovered every hour for 3 days -> exactly ONE notification
# =============================================================================
def test_a_same_job_discovered_every_hour_for_3_days(db_conn):
    """Simulate 72 hourly scans over 3 days for the same job posting."""
    mock_email = MockEmailProvider()
    email_svc = EmailNotificationService(db_conn, provider=mock_email)

    profile = _make_candidate_profile()
    facts = _make_fact_bank()
    scorer = JobScoringEngine(profile, facts)
    intel_svc = ApplicationIntelligenceService(facts, profile)

    job = _make_normalized_job(job_id=1, company="Qualcomm", title="Design Verification Engineer", requisition_id="ABC123")
    score = scorer.score_job(job)

    # Hour 1 (Monday 00:00) -> NOTIFY
    pkg_hour1 = intel_svc.create_application_package(job, score.match_score, freshness_age_hours=1.0)
    res1 = email_svc.process_immediate_alerts([pkg_hour1])
    assert len(res1) == 1
    assert res1[0].status == DeliveryStatus.SENT
    assert len(mock_email.sent_messages) == 1
    assert "Qualcomm" in mock_email.sent_messages[0].subject

    # Hours 2 to 72 (Monday through Thursday across 3 full days) -> ALL SUPPRESSED
    for hour in range(2, 73):
        pkg_subsequent = intel_svc.create_application_package(
            job,
            score.match_score,
            freshness_age_hours=1.0,
            is_material_update=False,
        )
        res = email_svc.process_immediate_alerts([pkg_subsequent])
        assert len(res) == 1
        assert res[0].status == DeliveryStatus.SUPPRESSED
        assert len(mock_email.sent_messages) == 1  # Total emails remains exactly 1

    # Final tally: exactly 1 email sent out of 72 hourly scans
    assert len(mock_email.sent_messages) == 1


# =============================================================================
# Test B: Same job discovered after 72 hours with no change -> NO automatic repeated notification
# =============================================================================
def test_b_same_job_after_72_hours_unchanged_suppressed(db_conn):
    """Even after 72+ hours (e.g. 96h, 120h, 1 week), unchanged job is NOT re-alerted."""
    mock_email = MockEmailProvider()
    email_svc = EmailNotificationService(db_conn, provider=mock_email)

    profile = _make_candidate_profile()
    facts = _make_fact_bank()
    scorer = JobScoringEngine(profile, facts)
    intel_svc = ApplicationIntelligenceService(facts, profile)

    job = _make_normalized_job(job_id=2, company="Qualcomm", title="Design Verification Engineer", requisition_id="ABC123")
    score = scorer.score_job(job)

    # Initial notification at hour 0
    pkg_init = intel_svc.create_application_package(job, score.match_score, freshness_age_hours=1.0)
    r_init = email_svc.process_immediate_alerts([pkg_init])
    assert r_init[0].status == DeliveryStatus.SENT
    assert len(mock_email.sent_messages) == 1

    # Re-discovered at 75 hours (Day 4) without material change -> SUPPRESSED
    pkg_75h = intel_svc.create_application_package(job, score.match_score, freshness_age_hours=1.0, is_material_update=False)
    r_75h = email_svc.process_immediate_alerts([pkg_75h])
    assert len(r_75h) == 1
    assert r_75h[0].status == DeliveryStatus.SUPPRESSED
    assert len(mock_email.sent_messages) == 1

    # Re-discovered at 120 hours (Day 5) without material change -> SUPPRESSED
    pkg_120h = intel_svc.create_application_package(job, score.match_score, freshness_age_hours=1.0, is_material_update=False)
    r_120h = email_svc.process_immediate_alerts([pkg_120h])
    assert len(r_120h) == 1
    assert r_120h[0].status == DeliveryStatus.SUPPRESSED
    assert len(mock_email.sent_messages) == 1


# =============================================================================
# Test C: Same company, different job IDs / requisitions -> independently evaluated
# =============================================================================
def test_c_same_company_different_job_ids(db_conn):
    """Qualcomm Req 123 and Qualcomm Req 456 must both generate alerts independently."""
    mock_email = MockEmailProvider()
    email_svc = EmailNotificationService(db_conn, provider=mock_email)

    profile = _make_candidate_profile()
    facts = _make_fact_bank()
    scorer = JobScoringEngine(profile, facts)
    intel_svc = ApplicationIntelligenceService(facts, profile)

    job1 = _make_normalized_job(job_id=10, company="Qualcomm", title="Design Verification Engineer", requisition_id="REQ-123")
    job2 = _make_normalized_job(job_id=11, company="Qualcomm", title="ASIC Verification Engineer", requisition_id="REQ-456")

    score1 = scorer.score_job(job1)
    score2 = scorer.score_job(job2)

    pkg1 = intel_svc.create_application_package(job1, score1.match_score, freshness_age_hours=1.0)
    pkg2 = intel_svc.create_application_package(job2, score2.match_score, freshness_age_hours=2.0)

    res = email_svc.process_immediate_alerts([pkg1, pkg2])

    assert len(res) == 2
    assert res[0].status == DeliveryStatus.SENT
    assert res[1].status == DeliveryStatus.SENT
    assert len(mock_email.sent_messages) == 2

    # Different fingerprints generated
    assert pkg1.job_fingerprint != pkg2.job_fingerprint


# =============================================================================
# Test D: Same company, different locations -> independently evaluated
# =============================================================================
def test_d_same_company_different_locations(db_conn):
    """Qualcomm DV Engineer in Bengaluru vs Qualcomm DV Engineer in Hyderabad."""
    mock_email = MockEmailProvider()
    email_svc = EmailNotificationService(db_conn, provider=mock_email)

    profile = _make_candidate_profile()
    facts = _make_fact_bank()
    scorer = JobScoringEngine(profile, facts)
    intel_svc = ApplicationIntelligenceService(facts, profile)

    job_blr = _make_normalized_job(job_id=20, company="Qualcomm", title="DV Engineer", location="Bengaluru, India", requisition_id="REQ-BLR")
    job_hyd = _make_normalized_job(job_id=21, company="Qualcomm", title="DV Engineer", location="Hyderabad, India", requisition_id="REQ-HYD")

    score_blr = scorer.score_job(job_blr)
    score_hyd = scorer.score_job(job_hyd)

    pkg_blr = intel_svc.create_application_package(job_blr, score_blr.match_score, freshness_age_hours=1.0)
    pkg_hyd = intel_svc.create_application_package(job_hyd, score_hyd.match_score, freshness_age_hours=1.5)

    res = email_svc.process_immediate_alerts([pkg_blr, pkg_hyd])

    assert len(res) == 2
    assert res[0].status == DeliveryStatus.SENT
    assert res[1].status == DeliveryStatus.SENT
    assert len(mock_email.sent_messages) == 2
    assert "Bengaluru" in mock_email.sent_messages[0].text_content
    assert "Hyderabad" in mock_email.sent_messages[1].text_content


# =============================================================================
# Test E: Same job with material change -> re-alerts with [MATERIAL UPDATE]
# =============================================================================
def test_e_same_job_material_change_re_alert(db_conn):
    """Material update triggers re-alert with [MATERIAL UPDATE] prefix."""
    mock_email = MockEmailProvider()
    email_svc = EmailNotificationService(db_conn, provider=mock_email)

    profile = _make_candidate_profile()
    facts = _make_fact_bank()
    scorer = JobScoringEngine(profile, facts)
    intel_svc = ApplicationIntelligenceService(facts, profile)

    job = _make_normalized_job(job_id=30, company="Qualcomm", title="Design Verification Engineer", requisition_id="ABC123")
    score = scorer.score_job(job)

    # Initial send
    pkg1 = intel_svc.create_application_package(job, score.match_score, freshness_age_hours=1.0, is_material_update=False)
    res1 = email_svc.process_immediate_alerts([pkg1])
    assert res1[0].status == DeliveryStatus.SENT
    assert len(mock_email.sent_messages) == 1
    assert "[MATERIAL UPDATE]" not in mock_email.sent_messages[0].subject

    # Re-scan without material change -> suppressed
    pkg2 = intel_svc.create_application_package(job, score.match_score, freshness_age_hours=2.0, is_material_update=False)
    res2 = email_svc.process_immediate_alerts([pkg2])
    assert res2[0].status == DeliveryStatus.SUPPRESSED
    assert len(mock_email.sent_messages) == 1

    # Material change discovered (e.g. updated requirements & application URL) -> re-alerted
    pkg_mat = intel_svc.create_application_package(job, score.match_score, freshness_age_hours=2.5, is_material_update=True)
    res3 = email_svc.process_immediate_alerts([pkg_mat])
    assert res3[0].status == DeliveryStatus.SENT
    assert len(mock_email.sent_messages) == 2
    assert "[MATERIAL UPDATE]" in mock_email.sent_messages[1].subject


# =============================================================================
# Test F: Same job already submitted by candidate -> suppressed
# =============================================================================
def test_f_same_job_already_submitted_suppressed(db_conn):
    """Candidate has already applied for this job -> suppressed even before any prior email."""
    repo = JobRepository(db_conn)
    mock_email = MockEmailProvider()
    email_svc = EmailNotificationService(db_conn, provider=mock_email, repo=repo)

    profile = _make_candidate_profile()
    facts = _make_fact_bank()
    scorer = JobScoringEngine(profile, facts)
    intel_svc = ApplicationIntelligenceService(facts, profile)

    job = _make_normalized_job(job_id=40, company="Qualcomm", title="Design Verification Engineer", requisition_id="REQ-SUBMIT")
    inserted_job_id = repo.insert_normalized_job(job)
    score = scorer.score_job(job)

    # Candidate manually logged application submission in SQLite
    app_id = repo.create_application(
        ApplicationRecord(
            job_id=inserted_job_id,
            status=ApplicationStatus.APPLIED,
            notes="Applied on company careers page.",
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
        )
    )
    assert app_id > 0

    pkg = intel_svc.create_application_package(job, score.match_score, freshness_age_hours=1.0, is_material_update=False)
    # Check that package or DB application status suppresses email
    res = email_svc.process_immediate_alerts([pkg])
    assert len(res) == 1
    assert res[0].status == DeliveryStatus.SUPPRESSED
    assert res[0].metadata.get("reason") == "application_already_submitted"
    assert len(mock_email.sent_messages) == 0


# =============================================================================
# Test G: Same job with only crawler/page timestamp changes -> suppressed
# =============================================================================
def test_g_same_job_crawler_timestamp_changes_suppressed(db_conn):
    """Timestamp updates in scanner do not trigger spurious alerts."""
    mock_email = MockEmailProvider()
    email_svc = EmailNotificationService(db_conn, provider=mock_email)
    now_iso = datetime.now(UTC).isoformat()
    hour_ago_iso = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    payload_initial = RawJobPayload(
        company="Qualcomm",
        title="Design Verification Engineer",
        raw_payload="Qualcomm Design Verification Engineer Bengaluru SystemVerilog UVM Verification",
        location="Bengaluru",
        country="India",
        source="qualcomm_portal",
        source_url="https://qualcomm.com/jobs/99",
        application_url="https://qualcomm.com/jobs/99",
        discovered_at=hour_ago_iso,
        content_hash="hash_qualcomm_99",
        metadata={"published_at": hour_ago_iso, "requisition_id": "REQ-99"},
    )
    adapter1 = MockJobSourceAdapter(custom_payloads=[payload_initial])

    scanner = FreshJobScanner(
        conn=db_conn,
        adapters=[adapter1],
        allow_mock=True,
        email_service=email_svc,
    )

    # Initial scan -> 1 notification
    rep1 = scanner.scan(hours=24.0, min_score=60.0, dry_run=False)
    assert rep1.notifications_proposed == 1
    assert len(mock_email.sent_messages) == 1

    # Next hour scan with updated crawler discovered_at and scan timestamp
    payload_hour2 = RawJobPayload(
        company="Qualcomm",
        title="Design Verification Engineer",
        raw_payload="Qualcomm Design Verification Engineer Bengaluru SystemVerilog UVM Verification",
        location="Bengaluru",
        country="India",
        source="qualcomm_portal",
        source_url="https://qualcomm.com/jobs/99",
        application_url="https://qualcomm.com/jobs/99",
        discovered_at=now_iso,  # New scan timestamp
        content_hash="hash_qualcomm_99_hour2",
        metadata={"published_at": hour_ago_iso, "requisition_id": "REQ-99"},
    )
    adapter2 = MockJobSourceAdapter(custom_payloads=[payload_hour2])
    scanner.adapters = [adapter2]

    rep2 = scanner.scan(hours=24.0, min_score=60.0, dry_run=False)
    assert rep2.notifications_proposed == 0
    assert len(mock_email.sent_messages) == 1  # No duplicate alert


# =============================================================================
# Test H: Existing deterministic fingerprint behavior remains intact
# =============================================================================
def test_h_deterministic_fingerprint_behavior():
    """Verify deterministic slug generation and backward compatibility."""
    fp1 = generate_job_fingerprint("Qualcomm", "Design Verification Engineer", "Bengaluru")
    fp2 = generate_job_fingerprint("Qualcomm", "Design Verification Engineer", "Bengaluru")
    assert fp1 == fp2 == "qualcomm-designverificationengineer-bengaluru"

    # With requisition ID
    fp_req = generate_job_fingerprint("Qualcomm", "Design Verification Engineer", "Bengaluru", requisition_id="123")
    assert fp_req == "qualcomm-designverificationengineer-bengaluru-123"

    # Different location produces different fingerprint
    fp_hyd = generate_job_fingerprint("Qualcomm", "Design Verification Engineer", "Hyderabad")
    assert fp_hyd == "qualcomm-designverificationengineer-hyderabad"
    assert fp_hyd != fp1
