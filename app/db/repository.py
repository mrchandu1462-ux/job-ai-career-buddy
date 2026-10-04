"""Parameterized repository operations for raw_jobs, normalized_jobs, applications, audit events, and notifications."""

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.db.models import (
    ApplicationEvent,
    ApplicationEventType,
    ApplicationRecord,
    ApplicationStatus,
    JobStatus,
    NormalizedJob,
    NotificationRecord,
    NotificationType,
    RawJob,
)


class DuplicateFingerprintError(Exception):
    """Raised when an attempt to insert a job with an existing fingerprint fails."""


class ApplicationNotFoundError(Exception):
    """Raised when an operation targets a non-existent application."""


class JobRepository:
    """Repository handling all parameterized SQL queries for jobs, applications, audit events, and notifications."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # -------------------------------------------------------------------------
    # Raw Jobs
    # -------------------------------------------------------------------------
    def insert_raw_job(self, raw_job: RawJob) -> int:
        """Insert a raw job record with parameterized SQL."""
        query = """
        INSERT INTO raw_jobs (source, source_url, discovered_at, raw_payload, content_hash)
        VALUES (?, ?, ?, ?, ?)
        """
        cursor = self.conn.execute(
            query,
            (
                raw_job.source,
                raw_job.source_url,
                raw_job.discovered_at,
                raw_job.raw_payload,
                raw_job.content_hash,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_raw_job(self, raw_job_id: int) -> RawJob | None:
        """Fetch a raw job by primary key id."""
        query = "SELECT * FROM raw_jobs WHERE id = ?"
        cursor = self.conn.execute(query, (raw_job_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return RawJob(
            id=row["id"],
            source=row["source"],
            source_url=row["source_url"],
            discovered_at=row["discovered_at"],
            raw_payload=row["raw_payload"],
            content_hash=row["content_hash"],
        )

    def get_raw_job_by_hash(self, content_hash: str) -> RawJob | None:
        """Fetch a raw job by content hash."""
        query = "SELECT * FROM raw_jobs WHERE content_hash = ?"
        cursor = self.conn.execute(query, (content_hash,))
        row = cursor.fetchone()
        if not row:
            return None
        return RawJob(
            id=row["id"],
            source=row["source"],
            source_url=row["source_url"],
            discovered_at=row["discovered_at"],
            raw_payload=row["raw_payload"],
            content_hash=row["content_hash"],
        )

    # -------------------------------------------------------------------------
    # Normalized Jobs
    # -------------------------------------------------------------------------
    def _row_to_normalized_job(self, row: sqlite3.Row) -> NormalizedJob:
        skills_raw = row["skills"]
        skills_list = json.loads(skills_raw) if skills_raw else []

        return NormalizedJob(
            id=row["id"],
            raw_job_id=row["raw_job_id"],
            company=row["company"],
            title=row["title"],
            location=row["location"],
            country=row["country"],
            employment_type=row["employment_type"],
            experience_min=row["experience_min"],
            experience_max=row["experience_max"],
            graduation_year_min=row["graduation_year_min"],
            graduation_year_max=row["graduation_year_max"],
            description=row["description"],
            requirements=row["requirements"],
            skills=skills_list,
            application_url=row["application_url"],
            source=row["source"],
            status=JobStatus(row["status"]),
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
            fingerprint=row["fingerprint"],
        )

    def insert_normalized_job(self, job: NormalizedJob) -> int:
        """Insert a normalized job. Raises DuplicateFingerprintError if fingerprint exists."""
        query = """
        INSERT INTO normalized_jobs (
            raw_job_id, company, title, location, country, employment_type,
            experience_min, experience_max, graduation_year_min, graduation_year_max,
            description, requirements, skills, application_url, source, status,
            first_seen, last_seen, fingerprint
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            cursor = self.conn.execute(
                query,
                (
                    job.raw_job_id,
                    job.company,
                    job.title,
                    job.location,
                    job.country,
                    job.employment_type,
                    job.experience_min,
                    job.experience_max,
                    job.graduation_year_min,
                    job.graduation_year_max,
                    job.description,
                    job.requirements,
                    json.dumps(job.skills),
                    job.application_url,
                    job.source,
                    job.status.value,
                    job.first_seen,
                    job.last_seen,
                    job.fingerprint,
                ),
            )
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint failed: normalized_jobs.fingerprint" in str(exc):
                raise DuplicateFingerprintError(
                    f"Job with fingerprint '{job.fingerprint}' already exists."
                ) from exc
            raise

    def get_normalized_job(self, job_id: int) -> NormalizedJob | None:
        """Fetch a normalized job by id."""
        query = "SELECT * FROM normalized_jobs WHERE id = ?"
        cursor = self.conn.execute(query, (job_id,))
        row = cursor.fetchone()
        return self._row_to_normalized_job(row) if row else None

    def get_normalized_job_by_fingerprint(self, fingerprint: str) -> NormalizedJob | None:
        """Fetch a normalized job by unique fingerprint."""
        query = "SELECT * FROM normalized_jobs WHERE fingerprint = ?"
        cursor = self.conn.execute(query, (fingerprint,))
        row = cursor.fetchone()
        return self._row_to_normalized_job(row) if row else None

    def list_normalized_jobs(
        self,
        status: JobStatus | str | None = None,
        company: str | None = None,
        location: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[NormalizedJob]:
        """Query normalized jobs with parameterized filters."""
        query = "SELECT * FROM normalized_jobs WHERE 1=1"
        params: list[Any] = []

        if status:
            status_val = status.value if isinstance(status, JobStatus) else status
            query += " AND status = ?"
            params.append(status_val)

        if company:
            query += " AND company = ?"
            params.append(company)

        if location:
            query += " AND location LIKE ?"
            params.append(f"%{location}%")

        query += " ORDER BY first_seen DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = self.conn.execute(query, tuple(params))
        return [self._row_to_normalized_job(row) for row in cursor.fetchall()]

    def count_normalized_jobs(self) -> int:
        """Count total normalized jobs."""
        cursor = self.conn.execute("SELECT COUNT(*) AS total FROM normalized_jobs")
        return cursor.fetchone()["total"]

    # -------------------------------------------------------------------------
    # Applications
    # -------------------------------------------------------------------------
    def _row_to_application_record(self, row: sqlite3.Row) -> ApplicationRecord:
        return ApplicationRecord(
            id=row["id"],
            job_id=row["job_id"],
            status=ApplicationStatus(row["status"]),
            notes=row["notes"],
            tailored_resume_path=row["tailored_resume_path"],
            cover_letter_path=row["cover_letter_path"],
            applied_at=row["applied_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_application(self, app_record: ApplicationRecord) -> int:
        """Create a new application tracking record."""
        query = """
        INSERT INTO applications (
            job_id, status, notes, tailored_resume_path, cover_letter_path,
            applied_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = self.conn.execute(
            query,
            (
                app_record.job_id,
                app_record.status.value,
                app_record.notes,
                app_record.tailored_resume_path,
                app_record.cover_letter_path,
                app_record.applied_at,
                app_record.created_at,
                app_record.updated_at,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_application(self, app_id: int) -> ApplicationRecord | None:
        """Fetch an application record by id."""
        query = "SELECT * FROM applications WHERE id = ?"
        cursor = self.conn.execute(query, (app_id,))
        row = cursor.fetchone()
        return self._row_to_application_record(row) if row else None

    def get_application_by_job_id(self, job_id: int) -> ApplicationRecord | None:
        """Fetch application record for a specific job."""
        query = "SELECT * FROM applications WHERE job_id = ?"
        cursor = self.conn.execute(query, (job_id,))
        row = cursor.fetchone()
        return self._row_to_application_record(row) if row else None

    def update_application_status(
        self,
        app_id: int,
        status: ApplicationStatus,
        notes: str | None = None,
        applied_at: str | None = None,
        tailored_resume_path: str | None = None,
        cover_letter_path: str | None = None,
    ) -> None:
        """Update the status, paths, and timestamps of an application."""
        now_iso = datetime.now(UTC).isoformat()
        query = """
        UPDATE applications
        SET status = ?,
            notes = COALESCE(?, notes),
            applied_at = COALESCE(?, applied_at),
            tailored_resume_path = COALESCE(?, tailored_resume_path),
            cover_letter_path = COALESCE(?, cover_letter_path),
            updated_at = ?
        WHERE id = ?
        """
        self.conn.execute(
            query,
            (
                status.value,
                notes,
                applied_at,
                tailored_resume_path,
                cover_letter_path,
                now_iso,
                app_id,
            ),
        )
        self.conn.commit()

    def list_applications(
        self, status: ApplicationStatus | None = None
    ) -> list[ApplicationRecord]:
        """List applications optionally filtered by lifecycle status."""
        query = "SELECT * FROM applications"
        params: list[Any] = []

        if status:
            query += " WHERE status = ?"
            params.append(status.value)

        query += " ORDER BY updated_at DESC"
        cursor = self.conn.execute(query, tuple(params))
        return [self._row_to_application_record(row) for row in cursor.fetchall()]

    # -------------------------------------------------------------------------
    # Application Events & Audit Trail
    # -------------------------------------------------------------------------
    def _row_to_application_event(self, row: sqlite3.Row) -> ApplicationEvent:
        return ApplicationEvent(
            id=row["id"],
            application_id=row["application_id"],
            job_id=row["job_id"],
            event_type=ApplicationEventType(row["event_type"]),
            company=row["company"],
            role_title=row["role_title"],
            location=row["location"],
            source=row["source"],
            official_application_url=row["official_application_url"],
            timestamp=row["timestamp"],
            resume_version=row["resume_version"],
            cover_letter_version=row["cover_letter_version"],
            application_status=ApplicationStatus(row["application_status"]),
            reference_id=row["reference_id"],
            submission_evidence=row["submission_evidence"],
            notes=row["notes"],
        )

    def record_application_event(self, event: ApplicationEvent) -> int:
        """Record an immutable audit log entry for an application action."""
        query = """
        INSERT INTO application_events (
            application_id, job_id, event_type, company, role_title, location,
            source, official_application_url, timestamp, resume_version,
            cover_letter_version, application_status, reference_id,
            submission_evidence, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = self.conn.execute(
            query,
            (
                event.application_id,
                event.job_id,
                event.event_type.value,
                event.company,
                event.role_title,
                event.location,
                event.source,
                event.official_application_url,
                event.timestamp,
                event.resume_version,
                event.cover_letter_version,
                event.application_status.value,
                event.reference_id,
                event.submission_evidence,
                event.notes,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_application_events(self, application_id: int) -> list[ApplicationEvent]:
        """Fetch all audit events for a given application in chronological order."""
        query = """
        SELECT * FROM application_events
        WHERE application_id = ?
        ORDER BY timestamp ASC, id ASC
        """
        cursor = self.conn.execute(query, (application_id,))
        return [self._row_to_application_event(row) for row in cursor.fetchall()]

    # -------------------------------------------------------------------------
    # Lifecycle Transitions with Safeguards
    # -------------------------------------------------------------------------
    def _get_app_and_job(self, app_id: int) -> tuple[ApplicationRecord, NormalizedJob]:
        app = self.get_application(app_id)
        if not app:
            raise ApplicationNotFoundError(f"Application id {app_id} not found.")
        job = self.get_normalized_job(app.job_id)
        if not job:
            raise ApplicationNotFoundError(f"Job id {app.job_id} not found for application {app_id}.")
        return app, job

    def open_application_page(
        self, app_id: int, page_url: str | None = None, notes: str | None = None
    ) -> ApplicationEvent:
        """Record that the application page was opened without changing application status to applied."""
        app, job = self._get_app_and_job(app_id)
        now_iso = datetime.now(UTC).isoformat()

        event = ApplicationEvent(
            application_id=app.id,
            job_id=job.id,
            event_type=ApplicationEventType.PAGE_OPENED,
            company=job.company,
            role_title=job.title,
            location=job.location,
            source=job.source,
            official_application_url=page_url or job.application_url,
            timestamp=now_iso,
            application_status=app.status,  # Preserves current status
            notes=notes or "Application portal page opened by candidate.",
        )
        self.record_application_event(event)
        return event

    def prepare_application(
        self,
        app_id: int,
        resume_path: str,
        cover_letter_path: str | None = None,
        notes: str | None = None,
    ) -> ApplicationEvent:
        """Advance application to 'preparing' and record artifacts without marking applied."""
        app, job = self._get_app_and_job(app_id)
        now_iso = datetime.now(UTC).isoformat()

        self.update_application_status(
            app_id=app_id,
            status=ApplicationStatus.PREPARING,
            notes=notes or "Artifacts assembled for preparation.",
            tailored_resume_path=resume_path,
            cover_letter_path=cover_letter_path,
        )

        event = ApplicationEvent(
            application_id=app.id,
            job_id=job.id,
            event_type=ApplicationEventType.PREPARED,
            company=job.company,
            role_title=job.title,
            location=job.location,
            source=job.source,
            official_application_url=job.application_url,
            timestamp=now_iso,
            resume_version=resume_path,
            cover_letter_version=cover_letter_path,
            application_status=ApplicationStatus.PREPARING,
            notes=notes or "Resume and artifacts prepared.",
        )
        self.record_application_event(event)
        return event

    def request_human_approval(
        self, app_id: int, notes: str | None = None
    ) -> ApplicationEvent:
        """Mark application as ready_for_review and trigger human approval notification."""
        app, job = self._get_app_and_job(app_id)
        now_iso = datetime.now(UTC).isoformat()

        self.update_application_status(
            app_id=app_id,
            status=ApplicationStatus.READY_FOR_REVIEW,
            notes=notes or "Awaiting candidate approval before submission.",
        )

        event = ApplicationEvent(
            application_id=app.id,
            job_id=job.id,
            event_type=ApplicationEventType.READY_FOR_REVIEW,
            company=job.company,
            role_title=job.title,
            location=job.location,
            source=job.source,
            official_application_url=job.application_url,
            timestamp=now_iso,
            resume_version=app.tailored_resume_path,
            cover_letter_version=app.cover_letter_path,
            application_status=ApplicationStatus.READY_FOR_REVIEW,
            notes=notes or "Application package ready for review.",
        )
        self.record_application_event(event)

        self.create_notification(
            NotificationRecord(
                application_id=app.id,
                job_id=job.id,
                notification_type=NotificationType.HUMAN_APPROVAL_REQUIRED,
                title="Review Required: Application Ready",
                message=f"Application for '{job.title}' at '{job.company}' is ready for your review and approval.",
                created_at=now_iso,
            )
        )
        return event

    def approve_application(
        self, app_id: int, notes: str | None = None
    ) -> ApplicationEvent:
        """Record candidate approval. Does NOT mark application as applied until submission is confirmed."""
        app, job = self._get_app_and_job(app_id)
        now_iso = datetime.now(UTC).isoformat()

        self.update_application_status(
            app_id=app_id,
            status=ApplicationStatus.APPROVED,
            notes=notes or "Application package approved by candidate for manual submission.",
        )

        event = ApplicationEvent(
            application_id=app.id,
            job_id=job.id,
            event_type=ApplicationEventType.APPROVED,
            company=job.company,
            role_title=job.title,
            location=job.location,
            source=job.source,
            official_application_url=job.application_url,
            timestamp=now_iso,
            resume_version=app.tailored_resume_path,
            cover_letter_version=app.cover_letter_path,
            application_status=ApplicationStatus.APPROVED,
            notes=notes or "Approved by candidate.",
        )
        self.record_application_event(event)
        return event

    def confirm_submission(
        self,
        app_id: int,
        official_application_url: str | None = None,
        reference_id: str | None = None,
        submission_evidence: str | None = None,
        notes: str | None = None,
    ) -> ApplicationEvent:
        """Confirm actual manual submission, transition to 'applied', and trigger success notification."""
        app, job = self._get_app_and_job(app_id)
        now_iso = datetime.now(UTC).isoformat()

        self.update_application_status(
            app_id=app_id,
            status=ApplicationStatus.APPLIED,
            applied_at=now_iso,
            notes=notes or "Application submitted manually by candidate.",
        )

        event = ApplicationEvent(
            application_id=app.id,
            job_id=job.id,
            event_type=ApplicationEventType.SUBMITTED,
            company=job.company,
            role_title=job.title,
            location=job.location,
            source=job.source,
            official_application_url=official_application_url or job.application_url,
            timestamp=now_iso,
            resume_version=app.tailored_resume_path,
            cover_letter_version=app.cover_letter_path,
            application_status=ApplicationStatus.APPLIED,
            reference_id=reference_id,
            submission_evidence=submission_evidence,
            notes=notes or "Confirmed submission recorded.",
        )
        self.record_application_event(event)

        self.create_notification(
            NotificationRecord(
                application_id=app.id,
                job_id=job.id,
                notification_type=NotificationType.SUBMISSION_SUCCESS,
                title="Application Submitted",
                message=f"Successfully submitted application for '{job.title}' at '{job.company}'"
                + (f" (Ref: {reference_id})" if reference_id else "."),
                created_at=now_iso,
            )
        )
        return event

    def record_submission_failure(
        self, app_id: int, error_notes: str, submission_evidence: str | None = None
    ) -> ApplicationEvent:
        """Record a submission failure, update status to 'failed', and trigger failure notification."""
        app, job = self._get_app_and_job(app_id)
        now_iso = datetime.now(UTC).isoformat()

        self.update_application_status(
            app_id=app_id,
            status=ApplicationStatus.FAILED,
            notes=f"Submission failed: {error_notes}",
        )

        event = ApplicationEvent(
            application_id=app.id,
            job_id=job.id,
            event_type=ApplicationEventType.SUBMISSION_FAILED,
            company=job.company,
            role_title=job.title,
            location=job.location,
            source=job.source,
            official_application_url=job.application_url,
            timestamp=now_iso,
            resume_version=app.tailored_resume_path,
            cover_letter_version=app.cover_letter_path,
            application_status=ApplicationStatus.FAILED,
            submission_evidence=submission_evidence,
            notes=error_notes,
        )
        self.record_application_event(event)

        self.create_notification(
            NotificationRecord(
                application_id=app.id,
                job_id=job.id,
                notification_type=NotificationType.SUBMISSION_FAILED,
                title="Application Submission Failed",
                message=f"Submission for '{job.title}' at '{job.company}' failed: {error_notes}",
                created_at=now_iso,
            )
        )
        return event

    # -------------------------------------------------------------------------
    # Notifications
    # -------------------------------------------------------------------------
    def _row_to_notification(self, row: sqlite3.Row) -> NotificationRecord:
        return NotificationRecord(
            id=row["id"],
            application_id=row["application_id"],
            job_id=row["job_id"],
            notification_type=NotificationType(row["notification_type"]),
            title=row["title"],
            message=row["message"],
            created_at=row["created_at"],
            is_read=bool(row["is_read"]),
        )

    def create_notification(self, notification: NotificationRecord) -> int:
        """Insert a notification record."""
        query = """
        INSERT INTO notifications (application_id, job_id, notification_type, title, message, created_at, is_read)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        cursor = self.conn.execute(
            query,
            (
                notification.application_id,
                notification.job_id,
                notification.notification_type.value,
                notification.title,
                notification.message,
                notification.created_at,
                1 if notification.is_read else 0,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def list_notifications(
        self,
        unread_only: bool = False,
        notification_type: NotificationType | None = None,
    ) -> list[NotificationRecord]:
        """Fetch notifications with optional unread and type filters."""
        query = "SELECT * FROM notifications WHERE 1=1"
        params: list[Any] = []

        if unread_only:
            query += " AND is_read = 0"

        if notification_type:
            query += " AND notification_type = ?"
            params.append(notification_type.value)

        query += " ORDER BY created_at DESC, id DESC"
        cursor = self.conn.execute(query, tuple(params))
        return [self._row_to_notification(row) for row in cursor.fetchall()]

    def mark_notification_read(self, notification_id: int) -> None:
        """Mark a notification as read."""
        query = "UPDATE notifications SET is_read = 1 WHERE id = ?"
        self.conn.execute(query, (notification_id,))
        self.conn.commit()
