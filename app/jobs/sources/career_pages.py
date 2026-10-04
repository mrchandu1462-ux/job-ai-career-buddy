"""Company career pages source adapter for top semiconductor and VLSI employers."""

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


class CompanyCareerSource(JobSource):
    """
    Job source for semiconductor company career portals
    (e.g., NVIDIA, Qualcomm, Intel, AMD, Texas Instruments, Synopsys, ARM, Cadence, Broadcom, MediaTek).
    """

    def __init__(self, company_name: str = "semiconductor_careers", verifier: ActiveStatusVerifier | None = None):
        self._source_name = f"careers_{company_name.lower().replace(' ', '_')}"
        self._verifier = verifier or ActiveStatusVerifier()
        self._postings: dict[str, RawJobPayload] = {}

    @property
    def source_name(self) -> str:
        return self._source_name

    def load_structured_postings(self, postings: list[dict[str, Any]]) -> list[RawJobPayload]:
        """Ingest a batch of structured career portal postings."""
        now_iso = datetime.now(UTC).isoformat()
        loaded = []
        for p in postings:
            company = str(p.get("company", "Semiconductor Employer")).strip()
            title = str(p.get("title", "Design Verification Engineer")).strip()
            raw_text = str(p.get("description", p.get("raw_payload", ""))).strip()
            location = p.get("location")
            country = p.get("country", "India")
            employment_type = p.get("employment_type", "Full-time")
            source_url = p.get("source_url") or p.get("url")
            application_url = p.get("application_url") or source_url

            content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
            payload = RawJobPayload(
                company=company,
                title=title,
                raw_payload=raw_text,
                location=location,
                country=country,
                employment_type=employment_type,
                source=self.source_name,
                source_url=source_url,
                application_url=application_url,
                discovered_at=now_iso,
                content_hash=content_hash,
                metadata=p.get("metadata", {}),
            )
            self._postings[content_hash] = payload
            loaded.append(payload)
        return loaded

    def search(self, query: JobDiscoveryQuery) -> list[RawJobPayload]:
        """Search company career postings matching query parameters."""
        results = []
        for payload in self._postings.values():
            text_to_search = f"{payload.company} {payload.title} {payload.raw_payload}".lower()

            # Keywords filter
            if query.keywords and not any(k.lower() in text_to_search for k in query.keywords):
                continue

            # Locations filter
            if query.locations and payload.location and not any(loc.lower() in payload.location.lower() for loc in query.locations):
                continue

            # Country filter
            if query.country and payload.country and query.country.lower() not in payload.country.lower():
                continue

            results.append(payload)
            if len(results) >= query.limit:
                break
        return results

    def fetch_job(self, source_identifier: str) -> RawJobPayload | None:
        """Fetch a specific posting by hash or URL."""
        if source_identifier in self._postings:
            return self._postings[source_identifier]
        for payload in self._postings.values():
            if payload.source_url == source_identifier or payload.application_url == source_identifier:
                return payload
        return None

    def normalize(self, payload: RawJobPayload, raw_job_id: int | None = None) -> NormalizedJob:
        """Convert payload to NormalizedJob."""
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
        """Verify active status against career portal rules."""
        return self._verifier.verify(payload)
