"""Pydantic models for end-to-end application lifecycle, matching explanations, exports, and audits."""

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import ApplicationStatus
from app.resume.export.models import ExportValidationReport


class CategorizedQuestionItem(BaseModel):
    """Interview question with clear distinction between historical facts and practice/generated items."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str
    topic: str
    difficulty: str | None = "medium"
    is_historical: bool = Field(..., description="True if asked in an actual verified past interview.")
    provenance_source: str = Field(..., description="Origin source (e.g. 'Qualcomm Tech Round 1', 'GENERATED / PRACTICE').")
    expected_answer: str | None = None
    frequency: int = 1
    weak_area_associated: bool = False


class ApplicationCandidateMatch(BaseModel):
    """Explainable candidate match report for a normalized job."""

    model_config = ConfigDict(extra="forbid")

    job_id: int
    company: str
    title: str
    match_score: float = Field(..., ge=0.0, le=100.0)
    is_eligible: bool
    role_category: str
    reasons_why: list[str] = Field(default_factory=list, description="Positive alignment factors.")
    skill_gaps: list[str] = Field(default_factory=list, description="Missing technical requirements.")
    adjacent_evidence: dict[str, str] = Field(default_factory=dict, description="Truthful adjacent evidence for gaps.")
    disqualification_reasons: list[str] = Field(default_factory=list)


class SubmissionRecord(BaseModel):
    """Audit payload for human-confirmed manual application submission."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    application_id: int
    job_id: int
    company: str
    role_title: str
    resume_version_used: str
    applied_at: str
    application_url: str | None = None
    reference_id: str | None = None
    submission_evidence: str | None = None
    notes: str | None = None


class SubmissionFailureRecord(BaseModel):
    """Audit payload for submission failure without falsely claiming APPLIED state."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    application_id: int
    job_id: int
    company: str
    role_title: str
    failed_at: str
    error_message: str
    evidence: str | None = None
    retry_recommendation: str = "Verify portal credentials, check URL reachability, and re-attempt submission."


class ApplicationPackageDetail(BaseModel):
    """
    Consolidated, auditable Application Package for a candidate opportunity:
    - Match evaluation & explanation
    - Fact-grounded tailored resume & versioning
    - ATS score & breakdown (target >= 80)
    - Validated exports (DOCX, PDF, TXT, MD)
    - Question pool separating historical vs generated/practice questions
    - Final assessment & readiness scoring
    - Preparation schedule & proposed milestones
    - Human approval boundaries & submission audit state
    """

    model_config = ConfigDict(extra="forbid")

    application_id: int | None = None
    job_id: int
    company: str
    title: str
    location: str | None = None
    country: str | None = None
    application_url: str | None = None
    status: ApplicationStatus = ApplicationStatus.DISCOVERED

    # Matching
    match: ApplicationCandidateMatch

    # Resume & ATS
    resume_id: str
    resume_version: int
    ats_score: float
    ats_quality_gate_met: bool
    fact_integrity_status: str
    unsupported_requirements: list[str] = Field(default_factory=list)
    adjacent_evidence_found: dict[str, str] = Field(default_factory=dict)

    # Exports & Validation
    docx_path: str | None = None
    pdf_path: str | None = None
    plaintext_path: str | None = None
    markdown_path: str | None = None
    docx_validation: ExportValidationReport | None = None
    pdf_validation: ExportValidationReport | None = None
    is_export_validated: bool = False

    # Interview Prep (Separated Historical vs Generated)
    historical_questions: list[CategorizedQuestionItem] = Field(default_factory=list)
    practice_questions: list[CategorizedQuestionItem] = Field(default_factory=list)
    weak_areas: list[str] = Field(default_factory=list)

    # Readiness & Schedule
    readiness_score: float | None = None
    readiness_status: str = "NOT_EVALUATED"
    critical_topics_passing: bool = False
    schedule_milestones: list[dict[str, str]] = Field(default_factory=list)

    # Human Approval & Audit Trail
    human_approval_state: str = "AWAITING_REVIEW"
    is_submitted: bool = False
    submission_record: SubmissionRecord | None = None
    submission_failure: SubmissionFailureRecord | None = None
    what_ai_did: list[str] = Field(default_factory=list)
    what_ai_did_not_do: list[str] = Field(default_factory=list)
    created_at: str
