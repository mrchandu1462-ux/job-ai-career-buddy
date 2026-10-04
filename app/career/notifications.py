"""Human-approved notification and calendar event proposal scheduling system."""

import sqlite3
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NotificationDispatchStatus(str, Enum):
    """Status of external schedule notification / calendar event dispatch."""

    PROPOSED = "proposed"  # Awaiting human approval
    APPROVED = "approved"  # User gave explicit approval
    REJECTED = "rejected"  # User declined the schedule
    DISPATCHED = "dispatched"  # Sent via external provider (mock/real)


class ProposedScheduleNotification(BaseModel):
    """Auditable proposal for an email reminder or calendar event."""

    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    notification_type: str = Field(..., description="'email_reminder', 'calendar_event', 'remediation_alert'")
    destination: str = Field(..., description="Target email or calendar provider (e.g. 'candidate@vlsi.ai', 'Google Calendar')")
    target_company: str
    target_role: str
    scheduled_time: str
    action_type: str = Field(..., description="'final_assessment', 'remediation_test', 'mock_drill', 'interview_day'")
    subject: str
    body_content: str
    rationale: str
    status: NotificationDispatchStatus = Field(default=NotificationDispatchStatus.PROPOSED)
    created_at: str
    approved_at: str | None = None
    dispatched_at: str | None = None


class ScheduleNotificationService:
    """Service managing draft schedule notifications and calendar events with mandatory human approval gates."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create proposed_schedule_notifications table if not present."""
        query = """
        CREATE TABLE IF NOT EXISTS proposed_schedule_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notification_type TEXT NOT NULL,
            destination TEXT NOT NULL,
            target_company TEXT NOT NULL,
            target_role TEXT NOT NULL,
            scheduled_time TEXT NOT NULL,
            action_type TEXT NOT NULL,
            subject TEXT NOT NULL,
            body_content TEXT NOT NULL,
            rationale TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            approved_at TEXT,
            dispatched_at TEXT
        )
        """
        self.conn.execute(query)
        self.conn.commit()

    def _row_to_proposal(self, row: sqlite3.Row) -> ProposedScheduleNotification:
        return ProposedScheduleNotification(
            id=row["id"],
            notification_type=row["notification_type"],
            destination=row["destination"],
            target_company=row["target_company"],
            target_role=row["target_role"],
            scheduled_time=row["scheduled_time"],
            action_type=row["action_type"],
            subject=row["subject"],
            body_content=row["body_content"],
            rationale=row["rationale"],
            status=NotificationDispatchStatus(row["status"]),
            created_at=row["created_at"],
            approved_at=row["approved_at"],
            dispatched_at=row["dispatched_at"],
        )

    def propose_schedule_notification(
        self,
        notification_type: str,
        destination: str,
        target_company: str,
        target_role: str,
        scheduled_time: str,
        action_type: str,
        subject: str,
        body_content: str,
        rationale: str,
    ) -> ProposedScheduleNotification:
        """Create a new proposed notification requiring explicit candidate approval before sending."""
        now_iso = datetime.now(UTC).isoformat()
        query = """
        INSERT INTO proposed_schedule_notifications (
            notification_type, destination, target_company, target_role,
            scheduled_time, action_type, subject, body_content, rationale,
            status, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = self.conn.execute(
            query,
            (
                notification_type,
                destination,
                target_company,
                target_role,
                scheduled_time,
                action_type,
                subject,
                body_content,
                rationale,
                NotificationDispatchStatus.PROPOSED.value,
                now_iso,
            ),
        )
        self.conn.commit()

        return ProposedScheduleNotification(
            id=cursor.lastrowid,
            notification_type=notification_type,
            destination=destination,
            target_company=target_company,
            target_role=target_role,
            scheduled_time=scheduled_time,
            action_type=action_type,
            subject=subject,
            body_content=body_content,
            rationale=rationale,
            status=NotificationDispatchStatus.PROPOSED,
            created_at=now_iso,
        )

    def list_proposals(
        self, status: NotificationDispatchStatus | str | None = None
    ) -> list[ProposedScheduleNotification]:
        """List schedule notification proposals, optionally filtered by status."""
        query = "SELECT * FROM proposed_schedule_notifications WHERE 1=1"
        params: list[Any] = []
        if status is not None:
            if isinstance(status, NotificationDispatchStatus):
                status_val = status.value
            elif isinstance(status, str):
                try:
                    status_val = NotificationDispatchStatus(status.lower()).value
                except ValueError:
                    raise ValueError(
                        f"Invalid notification dispatch status: '{status}'. "
                        f"Must be one of {[s.value for s in NotificationDispatchStatus]}"
                    )
            else:
                raise TypeError(
                    f"Expected NotificationDispatchStatus, str, or None, got {type(status).__name__}"
                )

            query += " AND status = ?"
            params.append(status_val)
        query += " ORDER BY id DESC"
        cursor = self.conn.execute(query, tuple(params))
        return [self._row_to_proposal(r) for r in cursor.fetchall()]

    def approve_proposal(self, proposal_id: int) -> ProposedScheduleNotification:
        """Explicit candidate approval for a proposed email or calendar event."""
        now_iso = datetime.now(UTC).isoformat()
        cursor = self.conn.execute(
            "SELECT * FROM proposed_schedule_notifications WHERE id = ?", (proposal_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Proposal #{proposal_id} not found.")

        self.conn.execute(
            "UPDATE proposed_schedule_notifications SET status = ?, approved_at = ? WHERE id = ?",
            (NotificationDispatchStatus.APPROVED.value, now_iso, proposal_id),
        )
        self.conn.commit()

        proposal = self._row_to_proposal(row)
        proposal.status = NotificationDispatchStatus.APPROVED
        proposal.approved_at = now_iso
        return proposal

    def reject_proposal(self, proposal_id: int) -> ProposedScheduleNotification:
        """Candidate rejection for a proposed email or calendar event."""
        cursor = self.conn.execute(
            "SELECT * FROM proposed_schedule_notifications WHERE id = ?", (proposal_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Proposal #{proposal_id} not found.")

        self.conn.execute(
            "UPDATE proposed_schedule_notifications SET status = ? WHERE id = ?",
            (NotificationDispatchStatus.REJECTED.value, proposal_id),
        )
        self.conn.commit()

        proposal = self._row_to_proposal(row)
        proposal.status = NotificationDispatchStatus.REJECTED
        return proposal
