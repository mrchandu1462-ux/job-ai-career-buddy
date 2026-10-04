"""Manual job source adapter for ingesting user-submitted or pasted job listings."""

import hashlib
from datetime import UTC, datetime

from app.db.models import NormalizedJob
from app.jobs.normalizer import normalize_job_listing
from app.jobs.sources.base import (
    ActiveVerificationResult,
    JobDiscoveryQuery,
    JobSource,
    RawJobPayload,
)
from app.jobs.verifier import ActiveStatusVerifier


class ManualJobSource(JobSource):
    """Job source handling manually provided job descriptions, structured inputs, or URLs."""

    def __init__(self, verifier: ActiveStatusVerifier | None = None):
        self._verifier = verifier or ActiveStatusVerifier()
        self._stored_jobs: dict[str, RawJobPayload] = {}

    @property
    def source_name(self) -> str:
        return "manual"

    def submit_manual_job(
        self,
        company: str,
        title: str,
        raw_text: str,
        location: str | None = None,
        country: str | None = "India",
        employment_type: str | None = "Full-time",
        source_url: str | None = None,
        application_url: str | None = None,
        metadata: dict | None = None,
    ) -> RawJobPayload:
        """Create and store a raw job payload from user input."""
        now_iso = datetime.now(UTC).isoformat()
        content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

        payload = RawJobPayload(
            company=company.strip(),
            title=title.strip(),
            raw_payload=raw_text.strip(),
            location=location.strip() if location else None,
            country=country.strip() if country else "India",
            employment_type=employment_type,
            source=self.source_name,
            source_url=source_url or application_url,
            application_url=application_url or source_url,
            discovered_at=now_iso,
            content_hash=content_hash,
            metadata=metadata or {},
        )
        self._stored_jobs[content_hash] = payload
        return payload

    def search(self, query: JobDiscoveryQuery) -> list[RawJobPayload]:
        """Search manually submitted listings by query keywords and locations."""
        results = []
        for payload in self._stored_jobs.values():
            text_to_search = f"{payload.company} {payload.title} {payload.raw_payload}".lower()
            if query.keywords and not any(k.lower() in text_to_search for k in query.keywords):
                continue
            if query.locations and payload.location and not any(loc.lower() in payload.location.lower() for loc in query.locations):
                continue
            results.append(payload)
            if len(results) >= query.limit:
                break
        return results

    def fetch_job(self, source_identifier: str) -> RawJobPayload | None:
        """Retrieve a stored manual job by content hash or direct URL."""
        if source_identifier in self._stored_jobs:
            return self._stored_jobs[source_identifier]
        for payload in self._stored_jobs.values():
            if payload.source_url == source_identifier or payload.application_url == source_identifier:
                return payload
        return None

    def normalize(self, payload: RawJobPayload, raw_job_id: int | None = None) -> NormalizedJob:
        """Convert raw payload into NormalizedJob."""
        return normalize_job_listing(
            company=payload.company,
            title=payload.title,
            raw_text=payload.raw_payload,
            location=payload.location,
            country=payload.country,
            employment_type=payload.employment_type,
            source=payload.source,
            application_url=payload.application_url or payload.source_url,
            raw_job_id=raw_job_id,
        )

    def verify_active(self, payload: RawJobPayload | NormalizedJob) -> ActiveVerificationResult:
        """Verify active status for manual job."""
        return self._verifier.verify(payload)
