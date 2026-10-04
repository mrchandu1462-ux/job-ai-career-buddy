"""Pydantic data models for Fact-Grounded Resumes, ATS scoring breakdowns, and integrity reports."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ResumeStatus(str, Enum):
    """Lifecycle status for a versioned tailored resume."""

    DRAFT = "draft"
    ATS_REVIEW = "ats_review"
    NEEDS_REVISION = "needs_revision"
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED = "approved"
    ARCHIVED = "archived"


class ResumeBullet(BaseModel):
    """Atomic resume bullet point grounded in verified candidate facts."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(..., min_length=10, description="Structured bullet text: Action + Method + Target + Result.")
    source_fact_ids: list[str] = Field(..., min_length=1, description="Fact IDs from FactBank that ground this claim.")
    verified: bool = Field(default=True, description="Whether the underlying facts are fully verified.")
    keywords_emphasized: list[str] = Field(default_factory=list, description="Keywords highlighted in this bullet.")


class ResumeProject(BaseModel):
    """Project section item grounded in verified project facts."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(..., min_length=3, description="Project title.")
    role: str | None = Field(default=None, description="Candidate role in the project.")
    technologies: list[str] = Field(default_factory=list, description="Technologies and EDA tools used.")
    bullets: list[ResumeBullet] = Field(..., min_length=1, description="Fact-grounded bullet points.")
    source_fact_id: str = Field(..., description="Root Fact ID for this project in FactBank.")


class ResumeExperience(BaseModel):
    """Work, internship, or training experience item."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(..., min_length=2, description="Job / Internship title.")
    company: str = Field(..., min_length=2, description="Company or Organization name.")
    location: str | None = Field(default=None, description="Location of work.")
    start_date: str | None = Field(default=None, description="Start date (e.g. 'Jan 2025').")
    end_date: str | None = Field(default=None, description="End date (e.g. 'May 2025' or 'Present').")
    bullets: list[ResumeBullet] = Field(default_factory=list, description="Experience bullet points.")
    source_fact_id: str = Field(..., description="Root Fact ID for this experience in FactBank.")


class ResumeEducation(BaseModel):
    """Education entry grounded in verified education facts."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    degree: str = Field(..., min_length=2, description="Degree name.")
    institution: str = Field(..., min_length=2, description="University / Institution name.")
    graduation_year: int = Field(..., ge=1990, le=2035, description="Graduation year.")
    gpa_or_score: str | None = Field(default=None, description="CGPA, GPA, or percentage.")
    source_fact_id: str = Field(..., description="Root Fact ID for this education entry in FactBank.")


class FactAuditReport(BaseModel):
    """Audit report validating that all claims in a resume map to verified facts."""

    model_config = ConfigDict(extra="forbid")

    total_claims: int = Field(..., ge=0)
    verified_claims: int = Field(..., ge=0)
    unverified_claims: int = Field(..., ge=0)
    unsupported_claims: list[str] = Field(default_factory=list)
    fabricated_metrics_detected: list[str] = Field(default_factory=list)
    integrity_status: str = Field(..., description="'PASS' or 'FAIL'")


class ATSBreakdown(BaseModel):
    """Explainable deterministic multi-dimensional ATS evaluation."""

    model_config = ConfigDict(extra="forbid")

    overall_score: float = Field(..., ge=0.0, le=100.0, description="Overall ATS Score out of 100.")
    technical_keyword_score: float = Field(..., ge=0.0, le=100.0, description="Technical keyword match score (30%).")
    required_skills_coverage: float = Field(..., ge=0.0, le=100.0, description="Required skills coverage score (30%).")
    project_relevance_score: float = Field(..., ge=0.0, le=100.0, description="Project relevance score (20%).")
    role_alignment_score: float = Field(..., ge=0.0, le=100.0, description="Role title alignment score (10%).")
    parser_safety_score: float = Field(..., ge=0.0, le=100.0, description="Parser safety score (10%).")
    parser_safety_status: str = Field(..., description="'PASS' or 'FAIL'")
    fact_integrity_status: str = Field(..., description="'PASS' or 'FAIL'")
    quality_gate_met: bool = Field(..., description="True if overall_score >= 80 and fact_integrity == 'PASS'.")
    matching_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    partial_matches: list[str] = Field(default_factory=list)
    unsupported_requirements: list[str] = Field(default_factory=list, description="Explicit list of JD requirements unsupported by verified candidate facts.")
    adjacent_evidence_found: dict[str, str] = Field(default_factory=dict, description="Truthful adjacent verified candidate evidence for missing or partial requirements.")
    potential_interview_risks: list[str] = Field(default_factory=list)
    score_rationale: list[str] = Field(default_factory=list)


class TailoredResume(BaseModel):
    """Complete, versioned, ATS-friendly, fact-grounded tailored resume."""

    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    resume_id: str = Field(..., min_length=3, description="Unique resume identifier.")
    target_job_id: int = Field(..., description="FK to normalized_jobs.id.")
    version: int = Field(default=1, ge=1, description="Version number for this job.")
    generated_at: str = Field(..., description="ISO-8601 creation timestamp.")
    candidate_name: str = Field(..., min_length=1)
    contact_info: dict[str, str] = Field(default_factory=dict)
    professional_summary: str = Field(..., min_length=20)
    technical_skills_by_category: dict[str, list[str]] = Field(default_factory=dict)
    projects: list[ResumeProject] = Field(default_factory=list)
    experience: list[ResumeExperience] = Field(default_factory=list)
    education: list[ResumeEducation] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    ats_score: float = Field(..., ge=0.0, le=100.0)
    ats_breakdown: ATSBreakdown
    fact_integrity_status: str = Field(..., description="'PASS' or 'FAIL'")
    source_fact_ids: list[str] = Field(default_factory=list)
    status: ResumeStatus = Field(default=ResumeStatus.DRAFT)
    plain_text_content: str | None = None
    markdown_content: str | None = None
