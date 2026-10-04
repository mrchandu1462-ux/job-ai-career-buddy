"""Job discovery, normalization, verification, classification, and ingestion package."""

from app.jobs.classifier import RoleCategory, RoleClassificationResult, RoleClassifier
from app.jobs.digest import DailyJobDigestService
from app.jobs.freshness import (
    calculate_alert_priority,
    calculate_fresh_job_priority_score,
    calculate_granular_freshness,
    calculate_job_freshness,
    classify_geography,
    classify_visa_sponsorship_category,
    extract_visa_sponsorship,
    extract_workplace_type,
)
from app.jobs.ingestion import IngestionReport, JobIngestInput, JobIngestionService
from app.jobs.models import (
    AlertPriority,
    FreshnessStatus,
    JobAlertRecord,
    JobSourceRunRecord,
    MonitoringCycleReport,
    SourceHealthStatus,
    VisaSponsorshipStatus,
    WorkplaceType,
)
from app.jobs.monitoring_service import FreshJobMonitoringService
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
from app.jobs.scanner import FreshJobScanner, ScanReport
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
from app.jobs.watchlist import CompanyWatchlistService

__all__ = [
    "ActiveStatusVerifier",
    "ActiveVerificationResult",
    "AlertPriority",
    "ApplicationPackage",
    "CompanyCareerSource",
    "CompanyWatchlistService",
    "DailyJobDigestService",
    "FreshJobMonitoringService",
    "FreshJobScanner",
    "FreshnessStatus",
    "IngestionReport",
    "JobActiveStatus",
    "JobAlertRecord",
    "JobDiscoveryPipeline",
    "JobDiscoveryQuery",
    "JobIngestInput",
    "JobIngestionService",
    "JobSource",
    "JobSourceRegistry",
    "JobSourceRunRecord",
    "ManualJobSource",
    "MonitoringCycleReport",
    "RawJobPayload",
    "RoleCategory",
    "RoleClassificationResult",
    "RoleClassifier",
    "ScanReport",
    "SourceHealthStatus",
    "StructuredJobBoardSource",
    "VisaSponsorshipStatus",
    "WorkplaceType",
    "calculate_alert_priority",
    "calculate_fresh_job_priority_score",
    "calculate_granular_freshness",
    "calculate_job_freshness",
    "classify_geography",
    "classify_visa_sponsorship_category",
    "detect_seniority_flag",
    "extract_experience_requirements",
    "extract_graduation_years",
    "extract_visa_sponsorship",
    "extract_vlsi_skills",
    "extract_workplace_type",
    "generate_job_fingerprint",
    "normalize_job_listing",
    "sync_job_status_from_verification",
]


