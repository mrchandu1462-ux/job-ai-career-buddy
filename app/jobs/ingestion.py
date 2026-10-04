"""Job discovery and ingestion service for raw & normalized job pipelines."""

import hashlib
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import (
    ApplicationEvent,
    ApplicationEventType,
    ApplicationRecord,
    ApplicationStatus,
    NormalizedJob,
    RawJob,
)
from app.db.repository import JobRepository
from app.jobs.normalizer import (
    detect_seniority_flag,
    normalize_job_listing,
)


class JobIngestInput(BaseModel):
    """Input payload representing a newly discovered job posting."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    company: str = Field(..., min_length=1, description="Company / Employer name.")
    title: str = Field(..., min_length=1, description="Job title.")
    raw_payload: str = Field(..., min_length=10, description="Raw job description or scraped payload.")
    location: str | None = Field(default=None, description="City / Location name.")
    country: str | None = Field(default="India", description="Country name.")
    employment_type: str | None = Field(default="Full-time", description="Employment type.")
    source: str = Field(default="manual", description="Source (e.g. 'company_portal', 'manual', 'linkedin').")
    source_url: str | None = Field(default=None, description="Direct URL of the listing.")
    application_url: str | None = Field(default=None, description="Official link to apply.")


class IngestionReport(BaseModel):
    """Result of an ingestion operation."""

    model_config = ConfigDict(extra="forbid")

    raw_job_id: int
    normalized_job_id: int
    is_new: bool
    fingerprint: str
    is_senior_role: bool
    extracted_skills_count: int
    application_id: int | None = None


class JobIngestionService:
    """Service that manages raw storage, normalization, deduplication, and initial application tracking."""

    def __init__(self, repo: JobRepository):
        self.repo = repo

    def ingest_job(self, input_data: JobIngestInput) -> IngestionReport:
        """
        Process a job posting:
        1. Store raw unmodified payload in raw_jobs with SHA-256 hash.
        2. Normalize fields (skills, experience, graduation year, fingerprint).
        3. Check for duplicates via fingerprint.
        4. If new, insert into normalized_jobs, create application in DISCOVERED status, and log audit event.
        5. If existing, update last_seen timestamp.
        """
        now_iso = datetime.now(UTC).isoformat()
        content_hash = hashlib.sha256(input_data.raw_payload.encode("utf-8")).hexdigest()

        # 1. Store Raw Job
        raw_job = RawJob(
            source=input_data.source,
            source_url=input_data.source_url or input_data.application_url,
            discovered_at=now_iso,
            raw_payload=input_data.raw_payload,
            content_hash=content_hash,
        )
        existing_raw = self.repo.get_raw_job_by_hash(content_hash)
        if existing_raw and existing_raw.id is not None:
            raw_id = existing_raw.id
        else:
            raw_id = self.repo.insert_raw_job(raw_job)

        # 2. Normalize Listing
        normalized: NormalizedJob = normalize_job_listing(
            company=input_data.company,
            title=input_data.title,
            raw_text=input_data.raw_payload,
            location=input_data.location,
            country=input_data.country,
            employment_type=input_data.employment_type,
            source=input_data.source,
            application_url=input_data.application_url or input_data.source_url,
            raw_job_id=raw_id,
        )

        fingerprint = normalized.fingerprint
        is_senior = detect_seniority_flag(normalized.title, normalized.experience_min)

        # 3. Check for Duplicate / Existing Normalized Job
        existing_job = self.repo.get_normalized_job_by_fingerprint(fingerprint)
        if existing_job and existing_job.id is not None:
            # Repost / already known listing: update last_seen timestamp
            self.repo.conn.execute(
                "UPDATE normalized_jobs SET last_seen = ? WHERE id = ?",
                (now_iso, existing_job.id),
            )
            self.repo.conn.commit()

            existing_app = self.repo.get_application_by_job_id(existing_job.id)
            app_id = existing_app.id if existing_app else None

            return IngestionReport(
                raw_job_id=raw_id,
                normalized_job_id=existing_job.id,
                is_new=False,
                fingerprint=fingerprint,
                is_senior_role=is_senior,
                extracted_skills_count=len(existing_job.skills),
                application_id=app_id,
            )

        # 4. Insert New Normalized Job
        normalized_id = self.repo.insert_normalized_job(normalized)

        # 5. Initialize Application Tracking Record
        app_record = ApplicationRecord(
            job_id=normalized_id,
            status=ApplicationStatus.DISCOVERED,
            notes=f"Discovered via {input_data.source}.",
            created_at=now_iso,
            updated_at=now_iso,
        )
        app_id = self.repo.create_application(app_record)

        # 6. Record Immutable Audit Event
        self.repo.record_application_event(
            ApplicationEvent(
                application_id=app_id,
                job_id=normalized_id,
                event_type=ApplicationEventType.JOB_DISCOVERED,
                company=normalized.company,
                role_title=normalized.title,
                location=normalized.location,
                source=normalized.source,
                official_application_url=normalized.application_url,
                timestamp=now_iso,
                application_status=ApplicationStatus.DISCOVERED,
                notes="Initial discovery and normalization.",
            )
        )

        return IngestionReport(
            raw_job_id=raw_id,
            normalized_job_id=normalized_id,
            is_new=True,
            fingerprint=fingerprint,
            is_senior_role=is_senior,
            extracted_skills_count=len(normalized.skills),
            application_id=app_id,
        )
