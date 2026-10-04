"""Pydantic models for hard eligibility filtering and deterministic relevance scoring."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.jobs.classifier import RoleClassificationResult


class EligibilityStatus(str, Enum):
    """Eligibility classification status."""

    ELIGIBLE = "ELIGIBLE"
    POSSIBLY_ELIGIBLE = "POSSIBLY_ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    UNKNOWN = "UNKNOWN"


class TechnicalSkillCategory(str, Enum):
    """Classification of technical skill match against verified candidate facts."""

    VERIFIED_MATCH = "VERIFIED_MATCH"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


class SkillMatchDetail(BaseModel):
    """Detailed breakdown for an individual skill requested by a job posting."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    skill_name: str
    category: TechnicalSkillCategory
    evidence_fact_id: str | None = None
    notes: str | None = None
    weight: float = 0.0


class HardFilterResult(BaseModel):
    """Outcome of hard eligibility rule evaluation."""

    model_config = ConfigDict(extra="forbid")

    is_eligible: bool
    status: EligibilityStatus = EligibilityStatus.ELIGIBLE
    passed_criteria: list[str] = Field(default_factory=list)
    failed_criteria: list[str] = Field(default_factory=list)
    is_overseas: bool = False
    requires_sponsorship: bool = False
    explanation: str = ""


class SoftScoreBreakdown(BaseModel):
    """Detailed point breakdown of deterministic relevance scoring."""

    model_config = ConfigDict(extra="forbid")

    skill_score: float = Field(..., ge=0.0, le=60.0)
    tools_score: float = Field(..., ge=0.0, le=20.0)
    location_score: float = Field(..., ge=0.0, le=10.0)
    role_fit_score: float = Field(..., ge=0.0, le=10.0)
    total_score: float = Field(..., ge=0.0, le=100.0)
    matching_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class JobScoreBreakdown7D(BaseModel):
    """
    Explainable 7-dimension job match score breakdown (0-100 total):
    - Role relevance: 20 pts
    - Technical skill match: 25 pts
    - Project alignment: 20 pts
    - Fresher / experience fit: 10 pts
    - Location preference: 10 pts
    - Interview knowledge relevance: 10 pts
    - Freshness / source quality: 5 pts
    """

    model_config = ConfigDict(extra="forbid")

    role_relevance: float = Field(..., ge=0.0, le=20.0, description="Role title/responsibility alignment (max 20 pts).")
    technical_match: float = Field(..., ge=0.0, le=25.0, description="Verified core VLSI/DV technical skills (max 25 pts).")
    project_alignment: float = Field(..., ge=0.0, le=20.0, description="Verified project and protocol experience (max 20 pts).")
    fresher_fit: float = Field(..., ge=0.0, le=10.0, description="Fresher / 2025 entry-level compatibility (max 10 pts).")
    location_preference: float = Field(..., ge=0.0, le=10.0, description="Tech hub location preference (max 10 pts).")
    interview_relevance: float = Field(..., ge=0.0, le=10.0, description="Available historical/curated interview intelligence (max 10 pts).")
    freshness_quality: float = Field(..., ge=0.0, le=5.0, description="Listing freshness and source provenance quality (max 5 pts).")
    total_score: float = Field(..., ge=0.0, le=100.0, description="Itemized total score (0-100).")
    role_classification: RoleClassificationResult | None = None
    skill_details: list[SkillMatchDetail] = Field(default_factory=list)
    itemized_reasons: list[str] = Field(default_factory=list)
    itemized_gaps: list[str] = Field(default_factory=list)


class JobMatchResult(BaseModel):
    """Comprehensive evaluation combining hard eligibility and soft match scoring."""

    model_config = ConfigDict(extra="forbid")

    job_id: int
    company: str
    title: str
    location: str | None = None
    country: str | None = None
    is_eligible: bool
    match_score: float = Field(..., ge=0.0, le=100.0)
    hard_filters: HardFilterResult
    score_breakdown: SoftScoreBreakdown
    breakdown_7d: JobScoreBreakdown7D | None = None
    is_overseas: bool = False
    requires_sponsorship: bool = False
    explanation: str
