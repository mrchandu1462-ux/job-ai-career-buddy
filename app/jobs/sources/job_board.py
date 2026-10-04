"""Job board and structured external API source adapter."""

import hashlib
from datetime import UTC, datetime
from typing import Any

from app.db.models import NormalizedJob
from app.jobs.normalizer import normalize_job_listing
from app.jobs.sources.base import (
    ActiveVerificationResult,
    JobDiscoveryQuery,
    JobSource,
    RawJobPayload,
)
from app.jobs.verifier import ActiveStatusVerifier


class StructuredJobBoardSource(JobSource):
    """Adapter for structured external job board listings (e.g. LinkedIn, Indeed, SemiconductorJobs)."""

    def __init__(self, board_name: str = "semiconductor_board", verifier: ActiveStatusVerifier | None = None):
        self._source_name = f"board_{board_name.lower().replace(' ', '_')}"
        self._verifier = verifier or ActiveStatusVerifier()
        self._jobs: dict[str, RawJobPayload] = {}

    @property
    def source_name(self) -> str:
        return self._source_name

    def ingest_api_feed(self, items: list[dict[str, Any]]) -> list[RawJobPayload]:
        """Ingest items from structured API responses or feeds."""
        now_iso = datetime.now(UTC).isoformat()
        ingested = []
        for item in items:
            company = str(item.get("company", "")).strip()
            title = str(item.get("title", "")).strip()
            raw_payload = str(item.get("description", item.get("raw_text", ""))).strip()
            location = item.get("location")
            country = item.get("country", "India")
            employment_type = item.get("employment_type", "Full-time")
            source_url = item.get("source_url") or item.get("url")
            application_url = item.get("application_url") or source_url

            content_hash = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()
            payload = RawJobPayload(
                company=company,
                title=title,
                raw_payload=raw_payload,
                location=location,
                country=country,
                employment_type=employment_type,
                source=self.source_name,
                source_url=source_url,
                application_url=application_url,
                discovered_at=now_iso,
                content_hash=content_hash,
                metadata=item.get("metadata", {}),
            )
            self._jobs[content_hash] = payload
            ingested.append(payload)
        return ingested

    def search(self, query: JobDiscoveryQuery) -> list[RawJobPayload]:
        """Search structured board jobs matching query."""
        results = []
        for payload in self._jobs.values():
            text_to_search = f"{payload.company} {payload.title} {payload.raw_payload}".lower()
            if query.keywords and not any(k.lower() in text_to_search for k in query.keywords):
                continue
            if query.locations and payload.location and not any(loc.lower() in payload.location.lower() for loc in query.locations):
                continue
            if query.country and payload.country and query.country.lower() not in payload.country.lower():
                continue
            results.append(payload)
            if len(results) >= query.limit:
                break
        return results

    def fetch_job(self, source_identifier: str) -> RawJobPayload | None:
        """Fetch by hash or URL."""
        if source_identifier in self._jobs:
            return self._jobs[source_identifier]
        for payload in self._jobs.values():
            if payload.source_url == source_identifier or payload.application_url == source_identifier:
                return payload
        return None

    def normalize(self, payload: RawJobPayload, raw_job_id: int | None = None) -> NormalizedJob:
        """Normalize payload."""
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
        """Verify active status."""
        return self._verifier.verify(payload)
