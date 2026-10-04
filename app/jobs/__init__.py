"""Job discovery, normalization, verification, classification, and ingestion package."""

from app.jobs.classifier import RoleCategory, RoleClassificationResult, RoleClassifier
from app.jobs.ingestion import IngestionReport, JobIngestInput, JobIngestionService
from app.jobs.normalizer import (
    detect_seniority_flag,
    extract_experience_requirements,
    extract_graduation_years,
    extract_vlsi_skills,
    generate_job_fingerprint,
    normalize_job_listing,
)
from app.jobs.package import ApplicationPackage
from app.jobs.pipeline import JobDiscoveryPipeline
from app.jobs.sources import (
    ActiveVerificationResult,
    CompanyCareerSource,
    JobActiveStatus,
    JobDiscoveryQuery,
    JobSource,
    JobSourceRegistry,
    ManualJobSource,
    RawJobPayload,
    StructuredJobBoardSource,
)
from app.jobs.verifier import ActiveStatusVerifier, sync_job_status_from_verification

__all__ = [
    "ActiveStatusVerifier",
    "ActiveVerificationResult",
    "ApplicationPackage",
    "CompanyCareerSource",
    "IngestionReport",
    "JobActiveStatus",
    "JobDiscoveryPipeline",
    "JobDiscoveryQuery",
    "JobIngestInput",
    "JobIngestionService",
    "JobSource",
    "JobSourceRegistry",
    "ManualJobSource",
    "RawJobPayload",
    "RoleCategory",
    "RoleClassificationResult",
    "RoleClassifier",
    "StructuredJobBoardSource",
    "detect_seniority_flag",
    "extract_experience_requirements",
    "extract_graduation_years",
    "extract_vlsi_skills",
    "generate_job_fingerprint",
    "normalize_job_listing",
    "sync_job_status_from_verification",
]
