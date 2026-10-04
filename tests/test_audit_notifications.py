"""Tests proving application audit trail, state protection, and notifications foundation."""

import pytest

from app.db.connection import get_db
from app.db.models import (
    ApplicationEventType,
    ApplicationRecord,
    ApplicationStatus,
    JobStatus,
    NormalizedJob,
    NotificationType,
)
from app.db.repository import JobRepository


@pytest.fixture
def repo():
    """Provides a fresh in-memory JobRepository."""
    with get_db(":memory:") as conn:
        yield JobRepository(conn)


@pytest.fixture
def sample_job_id(repo):
    """Inserts a sample normalized job for testing."""
    job = NormalizedJob(
        company="Synopsys India",
        title="Design Verification Engineer - Fresher",
        location="Bengaluru",
        country="India",
        employment_type="Full-time",
        experience_min=0.0,
        experience_max=1.0,
        graduation_year_min=2024,
        graduation_year_max=2025,
        skills=["SystemVerilog", "UVM", "Verilog"],
        application_url="https://synopsys.wd1.myworkdayjobs.com/careers/job-101",
        source="manual",
        status=JobStatus.ACTIVE,
        first_seen="2026-10-04T10:00:00Z",
        last_seen="2026-10-04T10:00:00Z",
        fingerprint="synopsys-dv-blr-2025-001",
    )
    return repo.insert_normalized_job(job)


@pytest.fixture
def sample_app_id(repo, sample_job_id):
    """Inserts a sample application record."""
    app = ApplicationRecord(
        job_id=sample_job_id,
        status=ApplicationStatus.DISCOVERED,
        created_at="2026-10-04T10:00:00Z",
        updated_at="2026-10-04T10:00:00Z",
    )
    return repo.create_application(app)


def test_opening_page_does_not_mark_as_applied(repo, sample_app_id):
    """Opening an application page records a PAGE_OPENED event but keeps status intact."""
    event = repo.open_application_page(
        app_id=sample_app_id,
        page_url="https://synopsys.wd1.myworkdayjobs.com/careers/job-101",
    )

    assert event.event_type == ApplicationEventType.PAGE_OPENED
    assert event.application_status == ApplicationStatus.DISCOVERED

    app = repo.get_application(sample_app_id)
    assert app.status == ApplicationStatus.DISCOVERED
    assert app.applied_at is None


def test_preparing_application_does_not_mark_as_applied(repo, sample_app_id):
    """Preparing an application sets status to PREPARING and records PREPARED, NOT APPLIED."""
    event = repo.prepare_application(
        app_id=sample_app_id,
        resume_path="/resumes/synopsys_dv_v1.pdf",
        cover_letter_path="/resumes/synopsys_cover_v1.pdf",
    )

    assert event.event_type == ApplicationEventType.PREPARED
    assert event.application_status == ApplicationStatus.PREPARING

    app = repo.get_application(sample_app_id)
    assert app.status == ApplicationStatus.PREPARING
    assert app.applied_at is None
    assert app.tailored_resume_path == "/resumes/synopsys_dv_v1.pdf"


def test_approval_does_not_mark_as_applied(repo, sample_app_id):
    """Requesting and granting human approval transitions to APPROVED, NOT APPLIED."""
    # Step 1: Request approval
    req_event = repo.request_human_approval(sample_app_id)
    assert req_event.event_type == ApplicationEventType.READY_FOR_REVIEW
    assert req_event.application_status == ApplicationStatus.READY_FOR_REVIEW

    app = repo.get_application(sample_app_id)
    assert app.status == ApplicationStatus.READY_FOR_REVIEW
    assert app.applied_at is None

    # Verify human approval notification created
    notifications = repo.list_notifications(
        notification_type=NotificationType.HUMAN_APPROVAL_REQUIRED
    )
    assert len(notifications) == 1
    assert "Review Required" in notifications[0].title

    # Step 2: Approve
    apprv_event = repo.approve_application(sample_app_id)
    assert apprv_event.event_type == ApplicationEventType.APPROVED
    assert apprv_event.application_status == ApplicationStatus.APPROVED

    app_after = repo.get_application(sample_app_id)
    assert app_after.status == ApplicationStatus.APPROVED
    assert app_after.applied_at is None


def test_only_confirmed_submission_creates_applied_event(repo, sample_app_id, sample_job_id):
    """Only an explicit submission confirmation transitions status to APPLIED and logs SUBMITTED."""
    event = repo.confirm_submission(
        app_id=sample_app_id,
        official_application_url="https://synopsys.wd1.myworkdayjobs.com/careers/job-101",
        reference_id="WD-2026-9988",
        submission_evidence="Confirmation email received with ref WD-2026-9988",
        notes="Candidate manually submitted on company portal.",
    )

    assert event.event_type == ApplicationEventType.SUBMITTED
    assert event.application_status == ApplicationStatus.APPLIED
    assert event.reference_id == "WD-2026-9988"
    assert event.submission_evidence is not None
    assert event.company == "Synopsys India"
    assert event.job_id == sample_job_id
    assert event.timestamp is not None

    app = repo.get_application(sample_app_id)
    assert app.status == ApplicationStatus.APPLIED
    assert app.applied_at is not None

    # Verify success notification
    notifications = repo.list_notifications(
        notification_type=NotificationType.SUBMISSION_SUCCESS
    )
    assert len(notifications) == 1
    assert "WD-2026-9988" in notifications[0].message


def test_failed_applications_distinguishable_from_successful(repo, sample_app_id):
    """Failed applications receive FAILED status, SUBMISSION_FAILED audit event, and distinct notification."""
    event = repo.record_submission_failure(
        app_id=sample_app_id,
        error_notes="Portal timeout while uploading verification project zip.",
        submission_evidence="HTTP 504 Gateway Timeout from portal",
    )

    assert event.event_type == ApplicationEventType.SUBMISSION_FAILED
    assert event.application_status == ApplicationStatus.FAILED
    assert event.notes == "Portal timeout while uploading verification project zip."

    app = repo.get_application(sample_app_id)
    assert app.status == ApplicationStatus.FAILED
    assert app.status != ApplicationStatus.APPLIED

    # Verify failure notification
    fail_notifications = repo.list_notifications(
        notification_type=NotificationType.SUBMISSION_FAILED
    )
    assert len(fail_notifications) == 1
    assert "Submission Failed" in fail_notifications[0].title


def test_application_events_chronological_audit_trail(repo, sample_app_id):
    """Full lifecycle records chronological audit events preserving references and timestamps."""
    repo.open_application_page(sample_app_id)
    repo.prepare_application(sample_app_id, resume_path="/resumes/v1.pdf")
    repo.request_human_approval(sample_app_id)
    repo.approve_application(sample_app_id)
    repo.confirm_submission(sample_app_id, reference_id="REF-12345")

    events = repo.get_application_events(sample_app_id)
    assert len(events) == 5

    event_types = [e.event_type for e in events]
    assert event_types == [
        ApplicationEventType.PAGE_OPENED,
        ApplicationEventType.PREPARED,
        ApplicationEventType.READY_FOR_REVIEW,
        ApplicationEventType.APPROVED,
        ApplicationEventType.SUBMITTED,
    ]

    for ev in events:
        assert ev.application_id == sample_app_id
        assert ev.company == "Synopsys India"
        assert ev.timestamp is not None


def test_notification_read_unread_flow(repo, sample_app_id):
    """Test notification unread filtering and marking as read."""
    repo.request_human_approval(sample_app_id)

    unread = repo.list_notifications(unread_only=True)
    assert len(unread) == 1

    repo.mark_notification_read(unread[0].id)
    unread_after = repo.list_notifications(unread_only=True)
    assert len(unread_after) == 0

    all_notifs = repo.list_notifications(unread_only=False)
    assert len(all_notifs) == 1
    assert all_notifs[0].is_read is True
