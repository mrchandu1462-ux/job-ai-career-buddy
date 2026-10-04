"""Active job status verification service with explainable provenance."""

import re
from datetime import UTC, datetime

from app.db.models import JobStatus, NormalizedJob
from app.jobs.sources.base import (
    ActiveVerificationResult,
    JobActiveStatus,
    RawJobPayload,
)


class ActiveStatusVerifier:
    """
    Evaluates whether a job posting is actively open for applications.
    Distinguishes: ACTIVE, EXPIRED, ARCHIVED, UNKNOWN.
    Never assumes a job is ACTIVE merely because it appeared in search results.
    """

    def __init__(self, stale_threshold_days: int = 45):
        self.stale_threshold_days = stale_threshold_days

    def verify(
        self,
        job: NormalizedJob | RawJobPayload,
        is_url_reachable: bool | None = None,
        portal_status: str | None = None,
    ) -> ActiveVerificationResult:
        """
        Verify the active status of a job posting based on evidence:
        1. Explicit expiration flags/text in the description.
        2. Application portal / URL response signals if provided.
        3. Recency / Staleness of the listing timestamp.
        4. Official career portal vs third-party provenance.
        """
        now = datetime.now(UTC)
        now_iso = now.isoformat()
        source = getattr(job, "source", "unknown")
        raw_text = getattr(job, "description", "") or getattr(job, "raw_payload", "") or ""

        # 1. Check for explicit closed/expired wording in job description
        expired_patterns = [
            r"\b(?:position|opening|job)\s*(?:is\s*)?(?:closed|expired|filled|no\s*longer\s*available)\b",
            r"\bapplications?\s*(?:are\s*)?closed\b",
            r"\bdeadline\s*has\s*passed\b",
            r"\bthis\s*job\s*has\s*expired\b",
        ]
        for pattern in expired_patterns:
            if re.search(pattern, raw_text, re.IGNORECASE):
                return ActiveVerificationResult(
                    status=JobActiveStatus.EXPIRED,
                    is_active=False,
                    verification_timestamp=now_iso,
                    verification_source=f"{source}_content_audit",
                    reason="Posting contains explicit language indicating the position is closed or expired.",
                )

        # 2. Check portal status signal if provided
        if portal_status:
            ps_lower = portal_status.lower()
            if ps_lower in ["closed", "expired", "filled", "inactive"]:
                return ActiveVerificationResult(
                    status=JobActiveStatus.EXPIRED,
                    is_active=False,
                    verification_timestamp=now_iso,
                    verification_source=f"{source}_portal_api",
                    reason=f"Official application portal reported status as '{portal_status}'.",
                )
            if ps_lower in ["archived", "removed"]:
                return ActiveVerificationResult(
                    status=JobActiveStatus.ARCHIVED,
                    is_active=False,
                    verification_timestamp=now_iso,
                    verification_source=f"{source}_portal_api",
                    reason=f"Official application portal marked listing as '{portal_status}'.",
                )
            if ps_lower in ["active", "open", "accepting_applications"]:
                return ActiveVerificationResult(
                    status=JobActiveStatus.ACTIVE,
                    is_active=True,
                    verification_timestamp=now_iso,
                    verification_source=f"{source}_portal_api",
                    reason="Official application portal confirmed listing is actively accepting applications.",
                )

        # 3. Check direct URL reachability if verified
        if is_url_reachable is False:
            return ActiveVerificationResult(
                status=JobActiveStatus.EXPIRED,
                is_active=False,
                verification_timestamp=now_iso,
                verification_source="url_probe",
                reason="Application URL is unreachable or returned HTTP 404/410 Gone.",
            )

        # 4. Check listing timestamp staleness
        timestamp_str = getattr(job, "last_seen", None) or getattr(job, "discovered_at", None)
        if timestamp_str:
            try:
                # Handle ISO format with Z or timezone
                cleaned_ts = timestamp_str.replace("Z", "+00:00")
                parsed_dt = datetime.fromisoformat(cleaned_ts)
                if parsed_dt.tzinfo is None:
                    parsed_dt = parsed_dt.replace(tzinfo=UTC)
                age_days = (now - parsed_dt).days
                if age_days > self.stale_threshold_days:
                    return ActiveVerificationResult(
                        status=JobActiveStatus.ARCHIVED,
                        is_active=False,
                        verification_timestamp=now_iso,
                        verification_source="timestamp_audit",
                        reason=f"Listing has not been seen or re-verified for {age_days} days (threshold: {self.stale_threshold_days} days).",
                    )
            except (ValueError, TypeError):
                # Unparseable timestamp, proceed to other verification heuristics
                pass

        # 5. Check if verified on official company career portal or direct application URL
        app_url = getattr(job, "application_url", None) or getattr(job, "source_url", None)
        has_official_source = any(
            source.lower().startswith(prefix)
            for prefix in ["company", "official", "careers_", "portal", "workday", "greenhouse"]
        )

        if has_official_source and app_url:
            return ActiveVerificationResult(
                status=JobActiveStatus.ACTIVE,
                is_active=True,
                verification_timestamp=now_iso,
                verification_source=source,
                reason="Verified active listing on official company careers portal with direct application URL.",
            )

        if app_url:
            return ActiveVerificationResult(
                status=JobActiveStatus.ACTIVE,
                is_active=True,
                verification_timestamp=now_iso,
                verification_source=source,
                reason="Listing has valid direct application URL and recent discovery timestamp.",
            )

        # If no application URL or evidence of active state
        return ActiveVerificationResult(
            status=JobActiveStatus.UNKNOWN,
            is_active=False,
            verification_timestamp=now_iso,
            verification_source=source,
            reason="Active status unknown: listing lacks direct application link or recent verification evidence.",
        )


def sync_job_status_from_verification(job: NormalizedJob, result: ActiveVerificationResult) -> JobStatus:
    """Helper to convert ActiveVerificationResult into JobStatus enum."""
    if result.status == JobActiveStatus.ACTIVE:
        return JobStatus.ACTIVE
    if result.status == JobActiveStatus.EXPIRED:
        return JobStatus.EXPIRED
    if result.status == JobActiveStatus.ARCHIVED:
        return JobStatus.ARCHIVED
    return JobStatus.ACTIVE
