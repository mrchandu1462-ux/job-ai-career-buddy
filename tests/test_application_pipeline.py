"""Comprehensive integration tests for End-to-End Application Pipeline Service."""

import pytest

from app.application.service import ApplicationPipelineService
from app.db.connection import get_db
from app.db.models import (
    ApplicationEventType,
    ApplicationStatus,
    InterviewQuestion,
    JobStatus,
    NormalizedJob,
    NotificationType,
)
from app.db.repository import JobRepository
from app.profile.models import (
    CandidateDetails,
    CandidateLocations,
    CandidateProfile,
    FactBank,
    FactCategory,
    FactItem,
    WorkAuthorization,
)


@pytest.fixture
def db_conn():
    with get_db(":memory:") as conn:
        yield conn


@pytest.fixture
def candidate_profile():
    return CandidateProfile(
        candidate=CandidateDetails(
            target_roles=["Design Verification Engineer", "ASIC Verification Engineer"],
            graduation_year=2025,
            experience_level="Fresher / Entry-Level",
            locations=CandidateLocations(
                india_priority=["Bengaluru", "Hyderabad", "Noida", "Chennai", "Pune"],
                overseas_enabled=True,
                overseas_require_sponsorship=True,
            ),
            work_authorization=WorkAuthorization(
                citizen_of="India",
                requires_sponsorship_overseas=True,
            ),
        )
    )


@pytest.fixture
def fact_bank():
    return FactBank(
        facts=[
            FactItem(
                fact_id="EDU-001",
                category=FactCategory.EDUCATION,
                subject="B.Tech in Electronics and Communication Engineering",
                value={"degree": "Bachelor of Technology", "institution": "National Institute of Technology", "graduation_year": 2025, "gpa": "7.38/10"},
                verified=True,
            ),
            FactItem(
                fact_id="SKILL-001",
                category=FactCategory.SKILL,
                subject="SystemVerilog",
                value={"skill_name": "SystemVerilog", "proficiency": "Advanced"},
                verified=True,
            ),
            FactItem(
                fact_id="SKILL-002",
                category=FactCategory.SKILL,
                subject="UVM",
                value={"skill_name": "UVM", "proficiency": "Intermediate"},
                verified=True,
            ),
            FactItem(
                fact_id="SKILL-003",
                category=FactCategory.SKILL,
                subject="AXI Protocol",
                value={"skill_name": "AXI4 Protocol", "proficiency": "Intermediate"},
                verified=True,
            ),
            FactItem(
                fact_id="SKILL-004",
                category=FactCategory.SKILL,
                subject="Async FIFO & CDC",
                value={"skill_name": "Async FIFO & CDC", "proficiency": "Intermediate"},
                verified=True,
            ),
            FactItem(
                fact_id="PROJ-001",
                category=FactCategory.PROJECT,
                subject="AXI4 Interface Verification IP",
                value={
                    "title": "AXI4 UVC Testbench Environment",
                    "technologies": ["SystemVerilog", "UVM", "QuestaSim", "SVA"],
                    "role": "Lead Verification Developer",
                    "bullets": [
                        "Architected modular UVM testbench comprising active master agent, monitor, and scoreboard.",
                        "Developed constrained-random sequence library generating single, incrementing, and wrap burst transfers.",
                        "Implemented SystemVerilog concurrent assertions (SVA) verifying VALID/READY handshakes.",
                    ],
                },
                verified=True,
            ),
            FactItem(
                fact_id="PROJ-002",
                category=FactCategory.PROJECT,
                subject="Async FIFO CDC Verification",
                value={
                    "title": "Dual-Clock Async FIFO Verification",
                    "technologies": ["Verilog", "SystemVerilog", "SVA", "ModelSim"],
                    "role": "Verification Developer",
                    "bullets": [
                        "Designed dual-clock asynchronous FIFO with 2-flip-flop synchronizers and Gray pointer conversion.",
                        "Verified full and empty condition flag generation logic preventing overflow.",
                    ],
                },
                verified=True,
            ),
        ]
    )


@pytest.fixture
def target_job(db_conn):
    job_repo = JobRepository(db_conn)
    job = NormalizedJob(
        company="Qualcomm India",
        title="Design Verification Engineer",
        location="Bengaluru",
        country="India",
        skills=["SystemVerilog", "UVM", "AXI Protocol", "Async FIFO", "SVA"],
        source="manual",
        status=JobStatus.ACTIVE,
        first_seen="2026-10-04T10:00:00Z",
        last_seen="2026-10-04T10:00:00Z",
        fingerprint="qualcomm-app-pipeline-test-01",
        application_url="https://qualcomm.wd5.myworkdayjobs.com/careers/job/dv-001",
    )
    job_id = job_repo.insert_normalized_job(job)
    job.id = job_id
    return job


def test_application_pipeline_end_to_end_preparation(tmp_path, db_conn, candidate_profile, fact_bank, target_job):
    """Test full preparation pipeline: matching, resume export validation, question pool separation, and ready for review status."""
    service = ApplicationPipelineService(
        conn=db_conn,
        profile=candidate_profile,
        fact_bank=fact_bank,
        artifacts_dir=str(tmp_path),
    )

    # Ingest a historical question to verify separation
    service.career_repo.insert_interview_question(
        InterviewQuestion(
            company="Qualcomm India",
            role="Design Verification Engineer",
            question="Explain the difference between uvm_driver and uvm_monitor.",
            topic="UVM",
            source="Qualcomm Tech Round 1",
            verified=True,
            created_at="2026-10-04T10:00:00Z",
        )
    )

    # 1. Shortlist Job
    shortlisted_app = service.shortlist_job(target_job.id)
    assert shortlisted_app.status == ApplicationStatus.SHORTLISTED

    # 2. Prepare Application Package
    package = service.prepare_application(job_id=target_job.id, target_interview_date="2026-10-15")

    assert package.status == ApplicationStatus.READY_FOR_REVIEW
    assert package.match.match_score >= 60.0
    assert package.ats_score >= 80.0
    assert package.fact_integrity_status == "PASS"

    # Verify Exports and Validation
    assert package.is_export_validated is True
    assert package.docx_path is not None and package.docx_validation.status == "PASS"
    assert package.pdf_path is not None and package.pdf_validation.status == "PASS"

    # Verify Separation of Historical vs Practice Questions
    assert len(package.historical_questions) >= 1
    assert any("uvm_driver and uvm_monitor" in q.question for q in package.historical_questions)
    assert all(q.is_historical is True for q in package.historical_questions)
    assert all(q.is_historical is False for q in package.practice_questions)

    # Verify Audit Events & Notifications
    events = service.job_repo.get_application_events(package.application_id)
    assert any(e.event_type == ApplicationEventType.READY_FOR_REVIEW for e in events)

    notifications = service.job_repo.list_notifications(unread_only=True)
    assert any(n.notification_type == NotificationType.HUMAN_APPROVAL_REQUIRED for n in notifications)


def test_application_review_and_confirmed_submission_flow(tmp_path, db_conn, candidate_profile, fact_bank, target_job):
    """Test human review decisions, confirmed submission audit, and failure auditing."""
    service = ApplicationPipelineService(
        conn=db_conn,
        profile=candidate_profile,
        fact_bank=fact_bank,
        artifacts_dir=str(tmp_path),
    )

    package = service.prepare_application(job_id=target_job.id)
    app_id = package.application_id

    # 1. Candidate Approves Package
    approved_app = service.review_application(app_id, decision="APPROVE", notes="Approved for submission.")
    assert approved_app.status == ApplicationStatus.APPROVED
    assert approved_app.status != ApplicationStatus.APPLIED  # Invariant: Approval is not submission

    # 2. Candidate Confirms Manual Submission
    sub_record = service.record_submission(
        application_id=app_id,
        reference_id="QUALCOMM-REQ-987654",
        submission_evidence="Screenshot of portal submission confirmation page",
        notes="Applied directly via Workday portal.",
    )

    assert sub_record.application_id == app_id
    assert sub_record.reference_id == "QUALCOMM-REQ-987654"

    # Check database state
    final_app = service.job_repo.get_application(app_id)
    assert final_app.status == ApplicationStatus.APPLIED
    assert final_app.applied_at is not None

    # Check SUBMITTED event and SUBMISSION_SUCCESS notification
    events = service.job_repo.get_application_events(app_id)
    assert any(e.event_type == ApplicationEventType.SUBMITTED for e in events)

    notifs = service.job_repo.list_notifications()
    assert any(n.notification_type == NotificationType.SUBMISSION_SUCCESS for n in notifs)


def test_submission_failure_auditing(tmp_path, db_conn, candidate_profile, fact_bank, target_job):
    """Test that a failed submission attempt records failure event without claiming APPLIED."""
    service = ApplicationPipelineService(
        conn=db_conn,
        profile=candidate_profile,
        fact_bank=fact_bank,
        artifacts_dir=str(tmp_path),
    )

    package = service.prepare_application(job_id=target_job.id)
    app_id = package.application_id

    service.review_application(app_id, decision="APPROVE")

    # Record failure
    failure_record = service.record_submission_failure(
        application_id=app_id,
        error_message="HTTP 504 Gateway Timeout on company portal during PDF upload.",
        evidence="Error response log snippet",
        retry_recommendation="Retry during off-peak hours or submit via email.",
    )

    assert failure_record.application_id == app_id
    assert "Gateway Timeout" in failure_record.error_message

    # Check application state
    app = service.job_repo.get_application(app_id)
    assert app.status == ApplicationStatus.FAILED
    assert app.applied_at is None  # Must NOT be marked as applied

    # Check audit trail
    events = service.job_repo.get_application_events(app_id)
    assert any(e.event_type == ApplicationEventType.SUBMISSION_FAILED for e in events)

    notifs = service.job_repo.list_notifications()
    assert any(n.notification_type == NotificationType.SUBMISSION_FAILED for n in notifs)
