"""Application Package data structure combining job data, eligibility, match score, resume, and interview prep."""

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import (
    ApplicationStatus,
    PreparationSchedule,
    ReadinessAssessment,
)
from app.jobs.classifier import RoleClassificationResult
from app.matching.models import HardFilterResult, JobMatchResult


class ApplicationPackage(BaseModel):
    """
    Consolidated Application Package for a target job opportunity.
    Unifies:
    1. Job information & provenance
    2. Hard eligibility filter result
    3. Itemized 7-dimension job match score
    4. Role classification
    5. Tailored resume candidate + ATS Score + Fact Integrity result
    6. Interview review pool & historical questions count
    7. Final assessment & readiness score
    8. Preparation schedule
    9. Official application URL & tracker state
    10. Transparent disclosure of AI actions vs Human approval boundaries
    """

    model_config = ConfigDict(extra="forbid")

    job_id: int
    company: str
    title: str
    location: str | None = None
    country: str | None = None
    application_url: str | None = None
    eligibility: HardFilterResult
    match_result: JobMatchResult
    role_classification: RoleClassificationResult
    tailored_resume_id: str | None = None
    ats_score: float | None = None
    ats_target_reached: bool = False
    missing_skills_for_ats: list[str] = Field(default_factory=list)
    fact_integrity_verified: bool = False
    interview_pool_size: int = 0
    historical_questions_count: int = 0
    expected_questions_count: int = 0
    weak_areas_count: int = 0
    readiness_assessment: ReadinessAssessment | None = None
    preparation_schedule: PreparationSchedule | None = None
    application_status: ApplicationStatus = ApplicationStatus.DISCOVERED
    human_approval_state: str = "AWAITING_REVIEW"
    what_ai_prepared: list[str] = Field(default_factory=list)
    what_ai_did_not_do: list[str] = Field(default_factory=list)
    generated_at: str
