"""Job source abstractions, query parameters, payloads, and active verification models."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import NormalizedJob


class JobActiveStatus(str, Enum):
    """Active listing status verification outcome."""

    ACTIVE = "active"
    EXPIRED = "expired"
    ARCHIVED = "archived"
    UNKNOWN = "unknown"


class ActiveVerificationResult(BaseModel):
    """Detailed result of job active status verification with provenance."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: JobActiveStatus = Field(..., description="Active status category.")
    is_active: bool = Field(..., description="Whether listing is actively open for applications.")
    verification_timestamp: str = Field(..., description="ISO-8601 UTC timestamp of verification.")
    verification_source: str = Field(..., description="Source used for verification (e.g. 'company_portal', 'url_check').")
    reason: str = Field(..., min_length=1, description="Transparent justification for the verification status.")


class RawJobPayload(BaseModel):
    """Discovered raw job payload with complete source provenance."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    company: str = Field(..., min_length=1, description="Company name.")
    title: str = Field(..., min_length=1, description="Job title.")
    raw_payload: str = Field(..., min_length=10, description="Raw job description or content.")
    location: str | None = Field(default=None, description="Job location.")
    country: str | None = Field(default="India", description="Country name.")
    employment_type: str | None = Field(default="Full-time", description="Employment type.")
    source: str = Field(..., min_length=1, description="Source name identifier.")
    source_url: str | None = Field(default=None, description="Direct URL to listing.")
    application_url: str | None = Field(default=None, description="Direct URL to application portal.")
    discovered_at: str = Field(..., description="ISO-8601 UTC discovery timestamp.")
    content_hash: str = Field(..., min_length=1, description="SHA-256 content hash.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional source metadata.")


class JobDiscoveryQuery(BaseModel):
    """Search query parameters for discovering jobs across sources."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    keywords: list[str] = Field(default_factory=list, description="Target search keywords (e.g. 'Design Verification', 'UVM').")
    locations: list[str] = Field(default_factory=list, description="Target locations (e.g. 'Bengaluru', 'Hyderabad').")
    country: str | None = Field(default=None, description="Target country.")
    include_internships: bool = Field(default=True, description="Whether to search for internships and trainee roles.")
    fresher_only: bool = Field(default=True, description="Whether to filter for entry-level and fresher compatible roles.")
    limit: int = Field(default=50, ge=1, le=500, description="Maximum number of listings to return.")


class JobSource(ABC):
    """Abstract base class for all job discovery sources."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique identifier name for this job source."""

    @abstractmethod
    def search(self, query: JobDiscoveryQuery) -> list[RawJobPayload]:
        """Search for relevant job postings matching the query."""

    @abstractmethod
    def fetch_job(self, source_identifier: str) -> RawJobPayload | None:
        """Fetch a specific job posting by URL or identifier."""

    @abstractmethod
    def normalize(self, payload: RawJobPayload, raw_job_id: int | None = None) -> NormalizedJob:
        """Convert a raw job payload into a validated NormalizedJob."""

    @abstractmethod
    def verify_active(self, payload: RawJobPayload | NormalizedJob) -> ActiveVerificationResult:
        """Verify if the job posting is currently active, expired, or archived."""
