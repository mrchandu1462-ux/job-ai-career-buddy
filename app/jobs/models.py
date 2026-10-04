from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import (
    AlertPriority,
    FreshnessStatus,
    JobAlertRecord,
    JobSourceRunRecord,
    SourceHealthStatus,
    VisaSponsorshipStatus,
    WorkplaceType,
)

__all__ = [
    "AlertPriority",
    "FreshnessStatus",
    "JobAlertRecord",
    "JobSourceRunRecord",
    "MonitoringCycleReport",
    "SourceHealthStatus",
    "VisaSponsorshipStatus",
    "WorkplaceType",
]



class MonitoringCycleReport(BaseModel):
    """Complete summary report of an automated or manual fresh job monitoring run."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    run_id: str = Field(..., description="Unique UUID for this monitoring cycle.")
    timestamp: str = Field(..., description="ISO-8601 UTC timestamp when run executed.")
    region: str = Field(default="all", description="Target region: 'india', 'overseas', 'all'")
    sources_checked: int = Field(default=0, ge=0)
    sources_successful: int = Field(default=0, ge=0)
    sources_failed: int = Field(default=0, ge=0)
    total_jobs_found: int = Field(default=0, ge=0)
    unique_jobs_ingested: int = Field(default=0, ge=0)
    fresh_24h_jobs_count: int = Field(default=0, ge=0)
    p0_count: int = Field(default=0, ge=0)
    p1_count: int = Field(default=0, ge=0)
    p2_count: int = Field(default=0, ge=0)
    p3_count: int = Field(default=0, ge=0)
    notifications_generated: int = Field(default=0, ge=0)
    source_health: dict[str, dict[str, Any]] = Field(default_factory=dict)
    alerts: list[JobAlertRecord] = Field(default_factory=list)
    dry_run: bool = Field(default=False, description="Whether cycle was executed in dry-run mode.")
