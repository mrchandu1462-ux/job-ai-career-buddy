"""Tests for Human-Approved Schedule Notifications and Calendar Event Proposals."""

import pytest

from app.career.notifications import (
    NotificationDispatchStatus,
    ScheduleNotificationService,
)
from app.db.connection import get_db


@pytest.fixture
def db_conn():
    with get_db(":memory:") as conn:
        yield conn


@pytest.fixture
def notification_service(db_conn):
    return ScheduleNotificationService(db_conn)


def test_propose_schedule_notification_starts_as_proposed(notification_service):
    """Test that all proposed notifications require explicit human approval and never auto-dispatch."""
    proposal = notification_service.propose_schedule_notification(
        notification_type="email_reminder",
        destination="candidate@vlsi-cos.internal",
        target_company="Qualcomm",
        target_role="Design Verification Engineer",
        scheduled_time="2026-10-06T19:00:00Z",
        action_type="final_assessment",
        subject="Your Qualcomm DV final assessment is scheduled for tomorrow at 7 PM.",
        body_content="Preparation schedule ready. Topics: SystemVerilog, UVM, AXI, CDC.",
        rationale="Target interview date in 2 days; candidate must complete final assessment.",
    )

    assert proposal.id is not None
    assert proposal.status == NotificationDispatchStatus.PROPOSED
    assert proposal.approved_at is None
    assert proposal.dispatched_at is None

    # Check listing
    pending = notification_service.list_proposals(status=NotificationDispatchStatus.PROPOSED)
    assert len(pending) == 1
    assert pending[0].id == proposal.id


def test_approve_and_reject_notification_gates(notification_service):
    """Test explicit human approval and rejection gates."""
    p1 = notification_service.propose_schedule_notification(
        notification_type="calendar_event",
        destination="Google Calendar",
        target_company="AMD",
        target_role="ASIC Verification Engineer",
        scheduled_time="2026-10-07T10:00:00Z",
        action_type="mock_drill",
        subject="AMD Verification Mock Drill",
        body_content="45-minute timed mock test on AXI & SVA.",
        rationale="Scheduled practice drill.",
    )

    p2 = notification_service.propose_schedule_notification(
        notification_type="email_reminder",
        destination="candidate@vlsi-cos.internal",
        target_company="Texas Instruments",
        target_role="ASIC Verification Engineer",
        scheduled_time="2026-10-08T15:00:00Z",
        action_type="remediation_test",
        subject="Your remediation test is ready.",
        body_content="15-minute test on Async FIFO mistakes.",
        rationale="Remediation for missed questions.",
    )

    # Human approves p1
    approved_p1 = notification_service.approve_proposal(p1.id)
    assert approved_p1.status == NotificationDispatchStatus.APPROVED
    assert approved_p1.approved_at is not None

    # Human rejects p2
    rejected_p2 = notification_service.reject_proposal(p2.id)
    assert rejected_p2.status == NotificationDispatchStatus.REJECTED

    # Verify state lists
    approved_list = notification_service.list_proposals(status=NotificationDispatchStatus.APPROVED)
    assert len(approved_list) == 1
    assert approved_list[0].target_company == "AMD"

    rejected_list = notification_service.list_proposals(status=NotificationDispatchStatus.REJECTED)
    assert len(rejected_list) == 1
    assert rejected_list[0].target_company == "Texas Instruments"


def test_list_proposals_status_type_normalization(notification_service):
    """Verify list_proposals correctly accepts enum, string (case-insensitive), None, and rejects invalid values."""
    p1 = notification_service.propose_schedule_notification(
        notification_type="email_reminder",
        destination="candidate@vlsi-cos.internal",
        target_company="Intel India",
        target_role="Design Verification Engineer",
        scheduled_time="2026-10-09T10:00:00Z",
        action_type="mock_drill",
        subject="Intel DV Preparation",
        body_content="Preparation drill.",
        rationale="Upcoming interview.",
    )
    notification_service.approve_proposal(p1.id)

    # 1. Test None returns all proposals
    all_props = notification_service.list_proposals(status=None)
    assert len(all_props) == 1

    # 2. Test Enum input
    approved_by_enum = notification_service.list_proposals(status=NotificationDispatchStatus.APPROVED)
    assert len(approved_by_enum) == 1
    assert approved_by_enum[0].id == p1.id

    # 3. Test String input (lowercase and uppercase)
    approved_by_str_lower = notification_service.list_proposals(status="approved")
    assert len(approved_by_str_lower) == 1

    approved_by_str_upper = notification_service.list_proposals(status="APPROVED")
    assert len(approved_by_str_upper) == 1

    proposed_by_str = notification_service.list_proposals(status="proposed")
    assert len(proposed_by_str) == 0

    # 4. Test Invalid status string raises ValueError
    with pytest.raises(ValueError, match="Invalid notification dispatch status"):
        notification_service.list_proposals(status="invalid_status_xyz")

    # 5. Test Invalid type raises TypeError
    with pytest.raises(TypeError, match="Expected NotificationDispatchStatus, str, or None"):
        notification_service.list_proposals(status=12345)

