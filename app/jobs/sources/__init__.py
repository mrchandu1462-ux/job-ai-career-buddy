"""Job discovery sources package."""

from app.jobs.sources.base import (
    ActiveVerificationResult,
    JobActiveStatus,
    JobDiscoveryQuery,
    JobSource,
    RawJobPayload,
)
from app.jobs.sources.career_pages import CompanyCareerSource
from app.jobs.sources.job_board import StructuredJobBoardSource
from app.jobs.sources.manual import ManualJobSource
from app.jobs.sources.registry import JobSourceRegistry

__all__ = [
    "ActiveVerificationResult",
    "CompanyCareerSource",
    "JobActiveStatus",
    "JobDiscoveryQuery",
    "JobSource",
    "JobSourceRegistry",
    "ManualJobSource",
    "RawJobPayload",
    "StructuredJobBoardSource",
]
