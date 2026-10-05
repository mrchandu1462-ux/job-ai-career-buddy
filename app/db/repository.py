"""Parameterized repository operations for raw_jobs, normalized_jobs, applications, audit events, and notifications."""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from app.db.models import (
    AlertPriority,
    ApplicationEvent,
    ApplicationEventType,
    ApplicationRecord,
    ApplicationStatus,
    CompanyWatchlistRecord,
    DeliveryStatus,
    EmailDeliveryRecord,
    FreshnessStatus,
    JobAlertRecord,
    JobPriorityCategory,
    JobSourceRunRecord,
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

        keys = row.keys() if hasattr(row, "keys") else []
        published_at = row["published_at"] if "published_at" in keys else None
        posted_at = row["posted_at"] if "posted_at" in keys else None
        discovered_at = row["discovered_at"] if "discovered_at" in keys else None
        source_timestamp = row["source_timestamp"] if "source_timestamp" in keys else None
        freshness_status = row["freshness_status"] if "freshness_status" in keys and row["freshness_status"] else "unknown"
        freshness_bucket = row["freshness_bucket"] if "freshness_bucket" in keys and row["freshness_bucket"] else "UNKNOWN"
        freshness_confidence = row["freshness_confidence"] if "freshness_confidence" in keys and row["freshness_confidence"] else "LOW"
        timestamp_source = row["timestamp_source"] if "timestamp_source" in keys and row["timestamp_source"] else "unverified"
        freshness_age_hours = row["freshness_age_hours"] if "freshness_age_hours" in keys else None
        region = row["region"] if "region" in keys and row["region"] else "india"
        city = row["city"] if "city" in keys else None
        workplace_type = row["workplace_type"] if "workplace_type" in keys and row["workplace_type"] else "unknown"
        remote_type = row["remote_type"] if "remote_type" in keys and row["remote_type"] else "unknown"
        visa_sponsorship = row["visa_sponsorship"] if "visa_sponsorship" in keys and row["visa_sponsorship"] else "unknown"
        visa_status = row["visa_status"] if "visa_status" in keys and row["visa_status"] else "unknown"
        sponsorship_confidence = row["sponsorship_confidence"] if "sponsorship_confidence" in keys and row["sponsorship_confidence"] else "LOW"
        source_name = row["source_name"] if "source_name" in keys else None
        source_type = row["source_type"] if "source_type" in keys and row["source_type"] else "career_pages"
        source_job_id = row["source_job_id"] if "source_job_id" in keys else None
        canonical_url = row["canonical_url"] if "canonical_url" in keys else None
        source_refs = (
            json.loads(row["source_references"])
            if "source_references" in keys and row["source_references"]
            else [row["source"]]
        )
        first_notified_at = row["first_notified_at"] if "first_notified_at" in keys else None
        last_notified_at = row["last_notified_at"] if "last_notified_at" in keys else None
        notification_count = row["notification_count"] if "notification_count" in keys and row["notification_count"] is not None else 0
        priority_score = row["priority_score"] if "priority_score" in keys and row["priority_score"] is not None else 0.0
        priority_category = row["priority_category"] if "priority_category" in keys and row["priority_category"] else "LOW"
        is_watchlist = bool(row["is_watchlist"]) if "is_watchlist" in keys and row["is_watchlist"] is not None else False

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
            published_at=published_at,
            posted_at=posted_at,
            discovered_at=discovered_at,
            source_timestamp=source_timestamp,
            freshness_status=freshness_status,
            freshness_bucket=freshness_bucket,
            freshness_confidence=freshness_confidence,
            timestamp_source=timestamp_source,
            freshness_age_hours=freshness_age_hours,
            region=region,
            city=city,
            workplace_type=workplace_type,
            remote_type=remote_type,
            visa_sponsorship=visa_sponsorship,
            visa_status=visa_status,
            sponsorship_confidence=sponsorship_confidence,
            source_name=source_name,
            source_type=source_type,
            source_job_id=source_job_id,
            canonical_url=canonical_url,
            source_references=source_refs,
            first_notified_at=first_notified_at,
            last_notified_at=last_notified_at,
            notification_count=notification_count,
            priority_score=priority_score,
            priority_category=priority_category,
            is_watchlist=is_watchlist,
        )

    def insert_normalized_job(self, job: NormalizedJob) -> int:
        """Insert a normalized job. Raises DuplicateFingerprintError if fingerprint exists."""
        query = """
        INSERT INTO normalized_jobs (
            raw_job_id, company, title, location, country, employment_type,
            experience_min, experience_max, graduation_year_min, graduation_year_max,
            description, requirements, skills, application_url, source, status,
            first_seen, last_seen, fingerprint, published_at, posted_at, discovered_at,
            source_timestamp, freshness_status, freshness_bucket, freshness_confidence,
            timestamp_source, freshness_age_hours, region, city, workplace_type,
            remote_type, visa_sponsorship, visa_status, sponsorship_confidence,
            source_name, source_type, source_job_id, canonical_url, source_references,
            first_notified_at, last_notified_at, notification_count, priority_score,
            priority_category, is_watchlist
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    job.published_at,
                    job.posted_at,
                    job.discovered_at,
                    job.source_timestamp,
                    job.freshness_status,
                    job.freshness_bucket,
                    job.freshness_confidence,
                    job.timestamp_source,
                    job.freshness_age_hours,
                    job.region,
                    job.city,
                    job.workplace_type,
                    job.remote_type,
                    job.visa_sponsorship,
                    job.visa_status,
                    job.sponsorship_confidence,
                    job.source_name,
                    job.source_type,
                    job.source_job_id,
                    job.canonical_url,
                    json.dumps(job.source_references or [job.source]),
                    job.first_notified_at,
                    job.last_notified_at,
                    job.notification_count,
                    job.priority_score,
                    job.priority_category,
                    1 if job.is_watchlist else 0,
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

    create_job = insert_normalized_job

    def get_normalized_job(self, job_id: int) -> NormalizedJob | None:
        """Fetch a normalized job by id."""
        query = "SELECT * FROM normalized_jobs WHERE id = ?"
        cursor = self.conn.execute(query, (job_id,))
        row = cursor.fetchone()
        return self._row_to_normalized_job(row) if row else None

    get_job_by_id = get_normalized_job

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
    # Scanner Lock Management
    # -------------------------------------------------------------------------
    def acquire_scanner_lock(self, lock_name: str, owner: str, lease_seconds: int = 300) -> bool:
        """Attempt to acquire a named scanner lock.
        Returns True if lock acquired, False if already held and not expired.
        """
        now = datetime.now(UTC)
        try:
            self.conn.execute(
                "INSERT INTO scanner_locks (lock_name, owner, acquired_at, lease_seconds) VALUES (?, ?, ?, ?)",
                (lock_name, owner, now.isoformat(), lease_seconds),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Lock already exists; check if it's expired
            row = self.conn.execute(
                "SELECT acquired_at, lease_seconds FROM scanner_locks WHERE lock_name = ?",
                (lock_name,)
            ).fetchone()
            if row:
                acquired_at = datetime.fromisoformat(row["acquired_at"])
                if acquired_at.tzinfo is None:
                    acquired_at = acquired_at.replace(tzinfo=UTC)
                existing_lease = row["lease_seconds"]
                if now - acquired_at > timedelta(seconds=existing_lease):
                    # Stale lock, replace it
                    self.conn.execute(
                        "UPDATE scanner_locks SET owner = ?, acquired_at = ?, lease_seconds = ? WHERE lock_name = ?",
                        (owner, now.isoformat(), lease_seconds, lock_name),
                    )
                    self.conn.commit()
                    return True
            return False

    def release_scanner_lock(self, lock_name: str, owner: str) -> None:
        """Release a scanner lock if owned by the caller."""
        self.conn.execute(
            "DELETE FROM scanner_locks WHERE lock_name = ? AND owner = ?",
            (lock_name, owner),
        )
        self.conn.commit()
    # -------------------------------------------------------------------------
    # Applications
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

    # -------------------------------------------------------------------------
    # Fresh Job Monitoring & Alerts (Phase 5)
    # -------------------------------------------------------------------------
    def record_source_run(self, record: JobSourceRunRecord) -> int:
        """Record audit details for a job source monitoring run."""
        query = """
        INSERT INTO job_source_runs (
            source_name, run_timestamp, status, jobs_discovered, jobs_accepted,
            jobs_rejected, fresh_jobs_count, duration_ms, error_message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = self.conn.execute(
            query,
            (
                record.source_name,
                record.run_timestamp,
                record.status,
                record.jobs_discovered,
                record.jobs_accepted,
                record.jobs_rejected,
                record.fresh_jobs_count,
                record.duration_ms,
                record.error_message,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def list_source_runs(
        self, source_name: str | None = None, limit: int = 20
    ) -> list[JobSourceRunRecord]:
        """List historical source execution runs."""
        query = "SELECT * FROM job_source_runs WHERE 1=1"
        params: list[Any] = []
        if source_name:
            query += " AND source_name = ?"
            params.append(source_name)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        cursor = self.conn.execute(query, tuple(params))
        records = []
        for r in cursor.fetchall():
            records.append(
                JobSourceRunRecord(
                    id=r["id"],
                    source_name=r["source_name"],
                    run_timestamp=r["run_timestamp"],
                    status=r["status"],
                    jobs_discovered=r["jobs_discovered"],
                    jobs_accepted=r["jobs_accepted"],
                    jobs_rejected=r["jobs_rejected"],
                    fresh_jobs_count=r["fresh_jobs_count"],
                    duration_ms=r["duration_ms"],
                    error_message=r["error_message"],
                )
            )
        return records


    def create_job_alert(self, alert: JobAlertRecord) -> int:
        """Persist a newly discovered opportunity alert."""
        query = """
        INSERT INTO job_alerts (
            job_id, company, title, location, country, published_at,
            freshness_status, freshness_age_hours, match_score, priority,
            status, notification_proposal_id, created_at,
            priority_category, is_fresh_24h_match, first_notified_at,
            last_notified_at, notification_count
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = self.conn.execute(
            query,
            (
                alert.job_id,
                alert.company,
                alert.title,
                alert.location,
                alert.country,
                alert.published_at,
                alert.freshness_status.value if isinstance(alert.freshness_status, FreshnessStatus) else str(alert.freshness_status),
                alert.freshness_age_hours,
                alert.match_score,
                alert.priority.value if isinstance(alert.priority, AlertPriority) else str(alert.priority),
                alert.status,
                alert.notification_proposal_id,
                alert.created_at,
                alert.priority_category.value if isinstance(alert.priority_category, JobPriorityCategory) else str(alert.priority_category),
                1 if alert.is_fresh_24h_match else 0,
                alert.first_notified_at,
                alert.last_notified_at,
                alert.notification_count,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def list_job_alerts(
        self,
        priority: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[JobAlertRecord]:
        """Fetch stored opportunity alerts with optional priority filter."""
        query = "SELECT * FROM job_alerts WHERE 1=1"
        params: list[Any] = []
        if priority and priority != "ALL":
            query += " AND (priority = ? OR priority_category = ?)"
            params.extend([priority, priority])
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        cursor = self.conn.execute(query, tuple(params))
        alerts = []
        for r in cursor.fetchall():
            keys = r.keys() if hasattr(r, "keys") else []
            p_cat = (
                JobPriorityCategory(r["priority_category"])
                if "priority_category" in keys and r["priority_category"] in [c.value for c in JobPriorityCategory]
                else JobPriorityCategory.LOW
            )
            is_24h = bool(r["is_fresh_24h_match"]) if "is_fresh_24h_match" in keys else False
            first_not = r["first_notified_at"] if "first_notified_at" in keys else None
            last_not = r["last_notified_at"] if "last_notified_at" in keys else None
            not_cnt = r["notification_count"] if "notification_count" in keys and r["notification_count"] is not None else 0

            alerts.append(
                JobAlertRecord(
                    id=r["id"],
                    job_id=r["job_id"],
                    company=r["company"],
                    title=r["title"],
                    location=r["location"],
                    country=r["country"],
                    published_at=r["published_at"],
                    freshness_status=FreshnessStatus(r["freshness_status"]) if r["freshness_status"] in [s.value for s in FreshnessStatus] else FreshnessStatus.UNKNOWN,
                    freshness_age_hours=r["freshness_age_hours"],
                    match_score=r["match_score"],
                    priority=AlertPriority(r["priority"]) if r["priority"] in [p.value for p in AlertPriority] else AlertPriority.UNKNOWN,
                    status=r["status"],
                    notification_proposal_id=r["notification_proposal_id"],
                    created_at=r["created_at"],
                    priority_category=p_cat,
                    is_fresh_24h_match=is_24h,
                    first_notified_at=first_not,
                    last_notified_at=last_not,
                    notification_count=not_cnt,
                )
            )
        return alerts

    def get_job_alert_by_job_id(self, job_id: int) -> JobAlertRecord | None:
        """Fetch alert record for a specific job_id if already generated."""
        query = "SELECT * FROM job_alerts WHERE job_id = ? ORDER BY id DESC LIMIT 1"
        cursor = self.conn.execute(query, (job_id,))
        r = cursor.fetchone()
        if not r:
            return None
        keys = r.keys() if hasattr(r, "keys") else []
        p_cat = (
            JobPriorityCategory(r["priority_category"])
            if "priority_category" in keys and r["priority_category"] in [c.value for c in JobPriorityCategory]
            else JobPriorityCategory.LOW
        )
        is_24h = bool(r["is_fresh_24h_match"]) if "is_fresh_24h_match" in keys else False
        first_not = r["first_notified_at"] if "first_notified_at" in keys else None
        last_not = r["last_notified_at"] if "last_notified_at" in keys else None
        not_cnt = r["notification_count"] if "notification_count" in keys and r["notification_count"] is not None else 0

        return JobAlertRecord(
            id=r["id"],
            job_id=r["job_id"],
            company=r["company"],
            title=r["title"],
            location=r["location"],
            country=r["country"],
            published_at=r["published_at"],
            freshness_status=FreshnessStatus(r["freshness_status"]) if r["freshness_status"] in [s.value for s in FreshnessStatus] else FreshnessStatus.UNKNOWN,
            freshness_age_hours=r["freshness_age_hours"],
            match_score=r["match_score"],
            priority=AlertPriority(r["priority"]) if r["priority"] in [p.value for p in AlertPriority] else AlertPriority.UNKNOWN,
            status=r["status"],
            notification_proposal_id=r["notification_proposal_id"],
            created_at=r["created_at"],
            priority_category=p_cat,
            is_fresh_24h_match=is_24h,
            first_notified_at=first_not,
            last_notified_at=last_not,
            notification_count=not_cnt,
        )

    def mark_job_notified(self, job_id: int) -> None:
        """Record timestamp and increment notification count for a notified job."""
        now_iso = datetime.now(UTC).isoformat()
        job = self.get_normalized_job(job_id)
        if not job:
            return
        first_notified = job.first_notified_at or now_iso
        new_count = (job.notification_count or 0) + 1
        query = """
        UPDATE normalized_jobs
        SET first_notified_at = ?,
            last_notified_at = ?,
            notification_count = ?
        WHERE id = ?
        """
        self.conn.execute(query, (first_notified, now_iso, new_count, job_id))

        # Also update job_alerts if present
        alert_query = """
        UPDATE job_alerts
        SET first_notified_at = COALESCE(first_notified_at, ?),
            last_notified_at = ?,
            notification_count = notification_count + 1
        WHERE job_id = ?
        """
        self.conn.execute(alert_query, (now_iso, now_iso, job_id))
        self.conn.commit()

    def update_normalized_job_freshness(
        self,
        job_id: int,
        freshness_status: str,
        freshness_age_hours: float | None,
        freshness_bucket: str = "UNKNOWN",
        freshness_confidence: str = "LOW",
        priority_score: float = 0.0,
        priority_category: str = "LOW",
        is_watchlist: bool = False,
    ) -> None:
        """Update freshness evaluation metrics on an existing normalized job."""
        query = """
        UPDATE normalized_jobs
        SET freshness_status = ?,
            freshness_age_hours = ?,
            freshness_bucket = ?,
            freshness_confidence = ?,
            priority_score = ?,
            priority_category = ?,
            is_watchlist = ?
        WHERE id = ?
        """
        self.conn.execute(
            query,
            (
                freshness_status,
                freshness_age_hours,
                freshness_bucket,
                freshness_confidence,
                priority_score,
                priority_category,
                1 if is_watchlist else 0,
                job_id,
            ),
        )
        self.conn.commit()

    def list_fresh_jobs(
        self,
        max_age_hours: float = 24.0,
        region: str | None = None,
        watchlist_only: bool = False,
        limit: int = 50,
    ) -> list[NormalizedJob]:
        """Fetch normalized jobs published within the specified maximum age."""
        query = "SELECT * FROM normalized_jobs WHERE status = 'active'"
        params: list[Any] = []
        if max_age_hours is not None:
            query += " AND (freshness_age_hours IS NOT NULL AND freshness_age_hours <= ?)"
            params.append(max_age_hours)
        if region and region.lower() == "india":
            query += " AND (country = 'India' OR location LIKE '%India%' OR location LIKE '%Bengaluru%' OR location LIKE '%Hyderabad%' OR region = 'india')"
        elif region and region.lower() == "overseas":
            query += " AND (country != 'India' AND country IS NOT NULL OR region = 'overseas')"
        if watchlist_only:
            query += " AND is_watchlist = 1"
        query += " ORDER BY COALESCE(priority_score, 0.0) DESC, first_seen DESC LIMIT ?"
        params.append(limit)

        cursor = self.conn.execute(query, tuple(params))
        return [self._row_to_normalized_job(row) for row in cursor.fetchall()]

    # -------------------------------------------------------------------------
    # Company Watchlist
    # -------------------------------------------------------------------------
    def list_watchlist(self, is_active: bool = True) -> list[CompanyWatchlistRecord]:
        """List configured target semiconductor companies on candidate watchlist."""
        query = "SELECT * FROM company_watchlist WHERE 1=1"
        params: list[Any] = []
        if is_active:
            query += " AND is_active = 1"
        query += " ORDER BY company_name ASC"
        cursor = self.conn.execute(query, tuple(params))
        records = []
        for r in cursor.fetchall():
            records.append(
                CompanyWatchlistRecord(
                    id=r["id"],
                    company_name=r["company_name"],
                    is_active=bool(r["is_active"]),
                    priority_level=r["priority_level"],
                    notes=r["notes"],
                    created_at=r["created_at"],
                )
            )
        return records

    def add_watchlist_company(
        self,
        company_name: str,
        priority_level: str = "HIGH",
        notes: str | None = None,
    ) -> int:
        """Add or re-activate a target company in the candidate watchlist."""
        now_iso = datetime.now(UTC).isoformat()
        check_q = "SELECT id FROM company_watchlist WHERE LOWER(company_name) = LOWER(?)"
        cursor = self.conn.execute(check_q, (company_name.strip(),))
        existing = cursor.fetchone()
        if existing:
            update_q = "UPDATE company_watchlist SET is_active = 1, priority_level = ?, notes = ? WHERE id = ?"
            self.conn.execute(update_q, (priority_level, notes, existing["id"]))
            self.conn.commit()
            return existing["id"]

        insert_q = """
        INSERT INTO company_watchlist (company_name, is_active, priority_level, notes, created_at)
        VALUES (?, 1, ?, ?, ?)
        """
        cur = self.conn.execute(insert_q, (company_name.strip(), priority_level, notes, now_iso))
        self.conn.commit()
        return cur.lastrowid

    def remove_watchlist_company(self, company_name: str) -> bool:
        """Remove a company from the candidate watchlist."""
        query = "DELETE FROM company_watchlist WHERE LOWER(company_name) = LOWER(?)"
        cursor = self.conn.execute(query, (company_name.strip(),))
        self.conn.commit()
        return cursor.rowcount > 0

    def is_company_in_watchlist(self, company_name: str) -> bool:
        """Check whether a given company is actively watched."""
        if not company_name:
            return False
        query = "SELECT 1 FROM company_watchlist WHERE LOWER(company_name) = LOWER(?) AND is_active = 1 LIMIT 1"
        cursor = self.conn.execute(query, (company_name.strip(),))
        return cursor.fetchone() is not None

    def get_watchlist_company(self, company_name: str) -> CompanyWatchlistRecord | None:
        """Fetch a specific company watchlist record by name."""
        if not company_name:
            return None
        query = "SELECT * FROM company_watchlist WHERE LOWER(company_name) = LOWER(?) LIMIT 1"
        cursor = self.conn.execute(query, (company_name.strip(),))
        row = cursor.fetchone()
        if not row:
            return None
        return CompanyWatchlistRecord(
            id=row["id"],
            company_name=row["company_name"],
            is_active=bool(row["is_active"]),
            priority_level=row["priority_level"],
            notes=row["notes"],
            created_at=row["created_at"],
        )

    def set_watchlist_company_active(self, company_name: str, is_active: bool) -> bool:
        """Enable or disable active status for a watchlist company."""
        query = "UPDATE company_watchlist SET is_active = ? WHERE LOWER(company_name) = LOWER(?)"
        cursor = self.conn.execute(query, (1 if is_active else 0, company_name.strip()))
        self.conn.commit()
        return cursor.rowcount > 0

    def set_watchlist_company_priority(self, company_name: str, priority_level: str) -> bool:
        """Update priority tier for a watchlist company."""
        query = "UPDATE company_watchlist SET priority_level = ? WHERE LOWER(company_name) = LOWER(?)"
        cursor = self.conn.execute(query, (priority_level.upper(), company_name.strip()))
        self.conn.commit()
        return cursor.rowcount > 0

    def seed_default_watchlist(self) -> list[str]:
        """Pre-populate top tier semiconductor companies into watchlist if empty."""
        defaults = [
            "NVIDIA",
            "Qualcomm",
            "AMD",
            "Intel",
            "Texas Instruments",
            "Arm",
            "Broadcom",
            "MediaTek",
            "Synopsys",
            "Cadence Design Systems",
            "Siemens EDA",
            "Marvell Technology",
            "Micron Technology",
            "Samsung Semiconductor",
            "Apple",
            "Google",
            "Microsoft",
            "NXP Semiconductors",
            "Infineon Technologies",
            "STMicroelectronics",
            "Renesas",
            "Analog Devices",
            "Microchip Technology",
            "Bosch",
            "L&T Semiconductor Technologies",
            "Tessolve",
            "eInfochips",
            "HCLTech",
            "Wipro VLSI",
            "SiFive",
            "Tenstorrent",
            "Groq",
            "Rivos",
        ]
        now_iso = datetime.now(UTC).isoformat()
        for comp in defaults:
            check = self.conn.execute(
                "SELECT 1 FROM company_watchlist WHERE LOWER(company_name) = LOWER(?)",
                (comp.lower(),),
            ).fetchone()
            if not check:
                self.conn.execute(
                    "INSERT INTO company_watchlist (company_name, is_active, priority_level, notes, created_at) VALUES (?, 1, 'HIGH', 'Top semiconductor firm', ?)",
                    (comp, now_iso),
                )
        self.conn.commit()
        return defaults

    def get_daily_digest_stats(self, hours: float = 24.0) -> dict[str, Any]:
        """Aggregate statistical metrics for the daily fresh job digest."""
        fresh_jobs = self.list_fresh_jobs(max_age_hours=hours, limit=500)
        india_jobs = [j for j in fresh_jobs if (j.region == "india" or (j.country and j.country.lower() == "india"))]
        overseas_jobs = [j for j in fresh_jobs if (j.region == "overseas" or (j.country and j.country.lower() != "india"))]
        critical_jobs = [j for j in fresh_jobs if j.priority_category == "CRITICAL" or j.priority_score >= 88.0]
        high_jobs = [j for j in fresh_jobs if j.priority_category == "HIGH" or (j.priority_score >= 75.0 and j.priority_score < 88.0)]
        watchlist_jobs = [j for j in fresh_jobs if j.is_watchlist]

        return {
            "total_fresh_24h": len(fresh_jobs),
            "india_fresh_count": len(india_jobs),
            "overseas_fresh_count": len(overseas_jobs),
            "critical_matches_count": len(critical_jobs),
            "high_matches_count": len(high_jobs),
            "watchlist_matches_count": len(watchlist_jobs),
            "top_fresh_jobs": fresh_jobs[:10],
            "india_top_jobs": india_jobs[:5],
            "overseas_top_jobs": overseas_jobs[:5],
        }

    # -------------------------------------------------------------------------
    # Phase 3: Scheduler / Monitor Daemon Persistent State
    # -------------------------------------------------------------------------

    def get_monitor_state_value(self, key: str) -> str | None:
        """Retrieve a single monitor-state value by key. Returns None if absent."""
        row = self.conn.execute(
            "SELECT value FROM monitor_state WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_monitor_state_value(self, key: str, value: str) -> None:
        """Upsert a monitor-state key/value pair with the current UTC timestamp."""
        now_iso = datetime.now(UTC).isoformat()
        self.conn.execute(
            """
            INSERT INTO monitor_state (key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, now_iso),
        )
        self.conn.commit()

    def get_scheduler_status(self) -> dict[str, Any]:
        """
        Return a dashboard-ready snapshot of the scheduler daemon state.

        Keys returned:
          - is_running (bool): True if a running marker has been persisted.
          - last_cycle_started_at (str | None): ISO-8601 UTC timestamp of the last cycle start.
          - last_cycle_completed_at (str | None): ISO-8601 UTC timestamp of the last completed cycle.
          - last_cycle_at (str | None): ISO-8601 UTC timestamp of the last completed cycle.
          - next_cycle_at (str | None): ISO-8601 UTC timestamp of the next scheduled cycle.
          - last_successful_scan_at (str | None): Timestamp of last successful scan.
          - last_failed_scan_at (str | None): Timestamp of last failed scan.
          - consecutive_failures (int): Count of consecutive failed cycles.
          - cycles_completed (int): Total successful cycles since daemon start.
          - cycles_failed (int): Total failed cycles since daemon start.
          - daemon_pid (int | None): PID of the daemon process, or None.
          - interval_minutes (int): Configured scan interval in minutes.
          - region (str): Configured region filter.
          - last_error (str | None): Last error message encountered.
          - jobs_discovered (int): Discovered jobs in most recent scan.
          - fresh_jobs (int): Fresh <=24h jobs in most recent scan.
          - india_jobs (int): India jobs in most recent scan.
          - overseas_jobs (int): Overseas jobs in most recent scan.
          - high_matches (int): High matches in most recent scan.
          - critical_matches (int): Critical matches in most recent scan.
          - notifications_proposed (int): Notifications proposed in most recent scan.
        """
        keys = [
            "scheduler_running",
            "last_cycle_started_at",
            "last_cycle_completed_at",
            "last_cycle_at",
            "next_cycle_at",
            "last_successful_scan_at",
            "last_failed_scan_at",
            "consecutive_failures",
            "cycles_completed",
            "cycles_failed",
            "daemon_pid",
            "interval_minutes",
            "scheduler_region",
            "last_error",
            "last_jobs_discovered",
            "last_fresh_24h",
            "last_india_count",
            "last_overseas_count",
            "last_high_matches",
            "last_critical_matches",
            "last_notifications_proposed",
        ]
        raw: dict[str, str | None] = {}
        for k in keys:
            raw[k] = self.get_monitor_state_value(k)

        last_cycle = raw.get("last_cycle_completed_at") or raw.get("last_cycle_at")

        return {
            "is_running": raw.get("scheduler_running") == "true",
            "last_cycle_started_at": raw.get("last_cycle_started_at"),
            "last_cycle_completed_at": last_cycle,
            "last_cycle_at": last_cycle,
            "next_cycle_at": raw.get("next_cycle_at"),
            "last_successful_scan_at": raw.get("last_successful_scan_at"),
            "last_failed_scan_at": raw.get("last_failed_scan_at"),
            "consecutive_failures": int(raw.get("consecutive_failures") or 0),
            "cycles_completed": int(raw.get("cycles_completed") or 0),
            "cycles_failed": int(raw.get("cycles_failed") or 0),
            "daemon_pid": int(raw["daemon_pid"]) if raw.get("daemon_pid") else None,
            "interval_minutes": int(raw.get("interval_minutes") or 60),
            "region": raw.get("scheduler_region") or "all",
            "last_error": raw.get("last_error"),
            "jobs_discovered": int(raw.get("last_jobs_discovered") or 0),
            "fresh_jobs": int(raw.get("last_fresh_24h") or 0),
            "india_jobs": int(raw.get("last_india_count") or 0),
            "overseas_jobs": int(raw.get("last_overseas_count") or 0),
            "high_matches": int(raw.get("last_high_matches") or 0),
            "critical_matches": int(raw.get("last_critical_matches") or 0),
            "notifications_proposed": int(raw.get("last_notifications_proposed") or 0),
        }

    # -------------------------------------------------------------------------
    # Email Notification Deliveries (Phase 4 Final Alert Automation)
    # -------------------------------------------------------------------------
    def create_email_delivery(self, record: EmailDeliveryRecord) -> int:
        """Insert an email delivery audit record."""
        query = """
        INSERT INTO email_deliveries (
            notification_id, job_id, application_id, recipient, priority, subject,
            delivery_status, provider, provider_message_id, attempt_count, created_at,
            queued_at, sent_at, failed_at, last_error, fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = self.conn.execute(
            query,
            (
                record.notification_id,
                record.job_id,
                record.application_id,
                record.recipient,
                record.priority,
                record.subject,
                record.delivery_status.value if isinstance(record.delivery_status, DeliveryStatus) else str(record.delivery_status),
                record.provider,
                record.provider_message_id,
                record.attempt_count,
                record.created_at,
                record.queued_at,
                record.sent_at,
                record.failed_at,
                record.last_error,
                record.fingerprint,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def update_email_delivery_status(
        self,
        delivery_id: int,
        status: DeliveryStatus | str,
        sent_at: str | None = None,
        failed_at: str | None = None,
        last_error: str | None = None,
        provider_message_id: str | None = None,
        attempt_increment: int = 1,
    ) -> None:
        """Update status, attempts, timestamps, and error on an email delivery record."""
        status_val = status.value if isinstance(status, DeliveryStatus) else str(status)
        query = """
        UPDATE email_deliveries
        SET delivery_status = ?,
            attempt_count = attempt_count + ?,
            sent_at = COALESCE(?, sent_at),
            failed_at = COALESCE(?, failed_at),
            last_error = COALESCE(?, last_error),
            provider_message_id = COALESCE(?, provider_message_id)
        WHERE id = ?
        """
        self.conn.execute(
            query,
            (status_val, attempt_increment, sent_at, failed_at, last_error, provider_message_id, delivery_id),
        )
        self.conn.commit()

    def get_email_delivery(self, delivery_id: int) -> EmailDeliveryRecord | None:
        """Fetch email delivery record by ID."""
        cursor = self.conn.execute("SELECT * FROM email_deliveries WHERE id = ?", (delivery_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_email_delivery(row)

    def get_email_delivery_by_fingerprint(self, fingerprint: str) -> EmailDeliveryRecord | None:
        """Fetch most recent email delivery record matching fingerprint."""
        query = "SELECT * FROM email_deliveries WHERE fingerprint = ? ORDER BY id DESC LIMIT 1"
        cursor = self.conn.execute(query, (fingerprint,))
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_email_delivery(row)

    def get_email_delivery_by_job_id(self, job_id: int) -> EmailDeliveryRecord | None:
        """Fetch most recent email delivery record for a given job."""
        query = "SELECT * FROM email_deliveries WHERE job_id = ? ORDER BY id DESC LIMIT 1"
        cursor = self.conn.execute(query, (job_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_email_delivery(row)

    def list_email_deliveries(
        self, status: str | None = None, limit: int = 50
    ) -> list[EmailDeliveryRecord]:
        """List email delivery records, optionally filtered by status."""
        if status:
            query = "SELECT * FROM email_deliveries WHERE delivery_status = ? ORDER BY id DESC LIMIT ?"
            cursor = self.conn.execute(query, (status, limit))
        else:
            query = "SELECT * FROM email_deliveries ORDER BY id DESC LIMIT ?"
            cursor = self.conn.execute(query, (limit,))
        return [self._row_to_email_delivery(r) for r in cursor.fetchall()]

    def get_email_delivery_stats(self) -> dict[str, Any]:
        """Return summary statistics for email deliveries."""
        cursor = self.conn.execute(
            """
            SELECT delivery_status, COUNT(*) as cnt
            FROM email_deliveries
            GROUP BY delivery_status
            """
        )
        counts: dict[str, int] = {
            "PROPOSED": 0,
            "QUEUED": 0,
            "SENDING": 0,
            "SENT": 0,
            "FAILED": 0,
            "SUPPRESSED": 0,
        }
        for row in cursor.fetchall():
            status_name = row["delivery_status"]
            counts[status_name] = row["cnt"]

        # Get last sent and failed timestamps
        last_sent_row = self.conn.execute(
            "SELECT sent_at FROM email_deliveries WHERE delivery_status = 'SENT' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        last_failed_row = self.conn.execute(
            "SELECT failed_at, last_error FROM email_deliveries WHERE delivery_status = 'FAILED' ORDER BY id DESC LIMIT 1"
        ).fetchone()

        return {
            "total": sum(counts.values()),
            "sent": counts["SENT"],
            "failed": counts["FAILED"],
            "suppressed": counts["SUPPRESSED"],
            "proposed": counts["PROPOSED"],
            "queued": counts["QUEUED"],
            "last_sent_at": last_sent_row["sent_at"] if last_sent_row else None,
            "last_failed_at": last_failed_row["failed_at"] if last_failed_row else None,
            "last_error": last_failed_row["last_error"] if last_failed_row else None,
        }

    def _row_to_email_delivery(self, row: sqlite3.Row) -> EmailDeliveryRecord:
        return EmailDeliveryRecord(
            id=row["id"],
            notification_id=row["notification_id"],
            job_id=row["job_id"],
            application_id=row["application_id"],
            recipient=row["recipient"],
            priority=row["priority"],
            subject=row["subject"],
            delivery_status=DeliveryStatus(row["delivery_status"]),
            provider=row["provider"],
            provider_message_id=row["provider_message_id"],
            attempt_count=row["attempt_count"],
            created_at=row["created_at"],
            queued_at=row["queued_at"],
            sent_at=row["sent_at"],
            failed_at=row["failed_at"],
            last_error=row["last_error"],
            fingerprint=row["fingerprint"],
        )



