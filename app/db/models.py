"""Pydantic models for jobs, applications, audit events, notifications, and career knowledge base."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ApplicationStatus(str, Enum):
    """Lifecycle stages for human-in-the-loop application tracking."""

    DISCOVERED = "discovered"
    REVIEWING = "reviewing"
    SHORTLISTED = "shortlisted"
    PREPARING = "preparing"
    READY_FOR_REVIEW = "ready_for_review"
    READY_TO_APPLY = "ready_to_apply"
    APPROVED = "approved"
    APPLIED = "applied"
    ASSESSMENT = "assessment"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    CLOSED = "closed"
    WITHDRAWN = "withdrawn"
    FAILED = "failed"


class ApplicationEventType(str, Enum):
    """Types of audit trail events recorded throughout the application lifecycle."""

    JOB_DISCOVERED = "job_discovered"
    PAGE_OPENED = "page_opened"
    PREPARED = "prepared"
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED = "approved"
    SUBMITTED = "submitted"
    SUBMISSION_FAILED = "submission_failed"
    STATUS_CHANGED = "status_changed"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class NotificationType(str, Enum):
    """Categories of notifications surfaced to the user."""

    SUBMISSION_SUCCESS = "submission_success"
    SUBMISSION_FAILED = "submission_failed"
    HUMAN_APPROVAL_REQUIRED = "human_approval_required"
    STATUS_CHANGED = "status_changed"


class JobStatus(str, Enum):
    """Status of job listing availability."""

    ACTIVE = "active"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class FreshnessStatus(str, Enum):
    """Categorized publication freshness status."""

    FRESH_0_6_HOURS = "fresh_0_6_hours"
    FRESH_6_24_HOURS = "fresh_6_24_hours"
    RECENT_1_3_DAYS = "recent_1_3_days"
    OLDER = "older"
    UNKNOWN = "unknown"


class FreshnessBucket(str, Enum):
    """Granular 24-hour publication freshness buckets."""

    LE_1_HOUR = "<= 1 hour"
    LE_3_HOURS = "<= 3 hours"
    LE_6_HOURS = "<= 6 hours"
    LE_12_HOURS = "<= 12 hours"
    LE_24_HOURS = "<= 24 hours"
    DAYS_1_3 = "1-3 days"
    DAYS_3_7 = "3-7 days"
    OLDER_7_DAYS = ">7 days"
    UNKNOWN = "UNKNOWN"


class FreshnessConfidence(str, Enum):
    """Confidence tier in verified publication timestamp."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class AlertPriority(str, Enum):
    """Priority level for human review notification proposals."""

    P0 = "P0"  # Published <24h with strong candidate match (>=75/80)
    P1 = "P1"  # Published <24h with reasonable candidate match (>=60)
    P2 = "P2"  # Published 1-3 days with strong match (>=80)
    P3 = "P3"  # Older or research opportunity
    UNKNOWN = "UNKNOWN"  # Unverified freshness or low match


class JobPriorityCategory(str, Enum):
    """Target opportunity classification priority category."""

    CRITICAL = "CRITICAL"  # 🔥 Fresh <=24h + excellent match (>=88/90)
    HIGH = "HIGH"  # 🟢 Fresh <=24h + strong match (>=75/80)
    GOOD = "GOOD"  # 🔵 Good match (>=60)
    MEDIUM = "MEDIUM"  # 🟡 Relevant / moderate match (>=60)
    WATCHLIST = "WATCHLIST"  # ⭐ Watchlisted employer
    LOW = "LOW"  # ⚪ Weak match (<50/60)
    REJECTED = "REJECTED"  # ❌ Ineligible / incompatible
    EXPIRED_STALE = "EXPIRED_STALE"  # 🔴 Outside freshness window / closed


class AlertMode(str, Enum):
    """Notification alert proposal filtering modes."""

    CRITICAL_ONLY = "CRITICAL_ONLY"
    HIGH_AND_CRITICAL = "HIGH_AND_CRITICAL"
    ALL_MATCHED = "ALL_MATCHED"
    WATCHLIST_COMPANIES = "WATCHLIST_COMPANIES"
    DAILY_DIGEST = "DAILY_DIGEST"
    HOURLY_CRITICAL = "HOURLY_CRITICAL"


class WorkplaceType(str, Enum):
    """Workplace arrangement setup."""

    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class VisaSponsorshipStatus(str, Enum):
    """Explicitly verified visa sponsorship availability."""

    AVAILABLE = "available"
    NOT_AVAILABLE = "not_available"
    CITIZEN_OR_PR_ONLY = "citizen_or_pr_only"
    UNKNOWN = "unknown"


class VisaSponsorshipCategory(str, Enum):
    """Explicit international visa sponsorship classification."""

    SPONSORSHIP_CONFIRMED = "SPONSORSHIP_CONFIRMED"
    SPONSORSHIP_POSSIBLE = "SPONSORSHIP_POSSIBLE"
    SPONSORSHIP_UNKNOWN = "SPONSORSHIP_UNKNOWN"
    SPONSORSHIP_NOT_SUPPORTED = "SPONSORSHIP_NOT_SUPPORTED"


class SourceHealthStatus(str, Enum):
    """Operational health status of an external job source adapter."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class FreshJobPriorityScore(BaseModel):
    """Explainable 8-dimensional fresh job priority score breakdown (out of 100)."""

    model_config = ConfigDict(extra="forbid")

    freshness: float = Field(..., ge=0.0, le=25.0, description="Freshness component (max 25).")
    technical_match: float = Field(..., ge=0.0, le=25.0, description="Technical skill match (max 25).")
    role_match: float = Field(..., ge=0.0, le=15.0, description="Role alignment (max 15).")
    project_relevance: float = Field(..., ge=0.0, le=10.0, description="Project alignment (max 10).")
    fresher_fit: float = Field(..., ge=0.0, le=10.0, description="Experience / fresher fit (max 10).")
    location_eligibility: float = Field(..., ge=0.0, le=5.0, description="Location & work eligibility (max 5).")
    company_confidence: float = Field(..., ge=0.0, le=5.0, description="Company watchlist & confidence (max 5).")
    application_accessibility: float = Field(..., ge=0.0, le=5.0, description="Direct application portal clarity (max 5).")
    total_score: float = Field(..., ge=0.0, le=100.0, description="Total explainable score (max 100).")
    category: JobPriorityCategory = Field(default=JobPriorityCategory.LOW)
    is_fresh_24h_match: bool = Field(default=False, description="Flag for special '🚨 FRESH 24H MATCH' badge.")


class CompanyWatchlistRecord(BaseModel):
    """Configured target semiconductor company on watchlist."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: int | None = None
    company_name: str = Field(..., min_length=1)
    is_active: bool = Field(default=True)
    priority_level: str = Field(default="HIGH", description="'CRITICAL', 'HIGH', 'STANDARD'")
    notes: str | None = None
    created_at: str


class JobSourceRunRecord(BaseModel):
    """Audit record for a single execution run of a job source adapter."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: int | None = None
    source_name: str = Field(..., min_length=1, description="Identifier of the source adapter.")
    run_timestamp: str = Field(..., description="ISO-8601 UTC timestamp of execution.")
    status: str = Field(..., description="'success', 'partial', 'failed'")
    jobs_discovered: int = Field(default=0, ge=0, description="Total raw jobs returned by adapter.")
    jobs_accepted: int = Field(default=0, ge=0, description="Valid normalized jobs accepted.")
    jobs_rejected: int = Field(default=0, ge=0, description="Invalid/malformed jobs rejected.")
    fresh_jobs_count: int = Field(default=0, ge=0, description="Jobs published within last 24 hours.")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Execution duration in milliseconds.")
    error_message: str | None = Field(default=None, description="Error or failure message if degraded/failed.")


class JobAlertRecord(BaseModel):
    """Stored opportunity alert surfaced for human review."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: int | None = None
    job_id: int = Field(..., description="ID of normalized_jobs record.")
    company: str
    title: str
    location: str | None = None
    country: str | None = "India"
    published_at: str | None = None
    freshness_status: FreshnessStatus = FreshnessStatus.UNKNOWN
    freshness_age_hours: float | None = None
    match_score: float = Field(..., ge=0.0, le=100.0)
    priority: AlertPriority = AlertPriority.UNKNOWN
    status: str = Field(default="proposed", description="'proposed', 'approved', 'dismissed'")
    notification_proposal_id: int | None = Field(default=None, description="Linked proposed_schedule_notifications id.")
    created_at: str
    priority_category: JobPriorityCategory = JobPriorityCategory.LOW
    is_fresh_24h_match: bool = False
    first_notified_at: str | None = None
    last_notified_at: str | None = None
    notification_count: int = 0




class RawJob(BaseModel):
    """Original untouched job listing payload directly from source."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: int | None = None
    source: str = Field(..., min_length=1, description="Origin of listing (e.g., 'manual', 'portal').")
    source_url: str | None = Field(default=None, description="Direct URL of the listing.")
    discovered_at: str = Field(..., description="ISO-8601 UTC timestamp of discovery.")
    raw_payload: str = Field(..., min_length=1, description="Original raw payload/content.")
    content_hash: str = Field(..., min_length=1, description="SHA256 hash of raw payload.")


class NormalizedJob(BaseModel):
    """Standardized and cleaned job record ready for deterministic filtering and ranking."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: int | None = None
    raw_job_id: int | None = Field(default=None, description="Reference to raw_jobs record if applicable.")
    company: str = Field(..., min_length=1, description="Company / Employer name.")
    title: str = Field(..., min_length=1, description="Job title.")
    location: str | None = Field(default=None, description="City / Region / Remote status.")
    country: str | None = Field(default=None, description="Country name or ISO code.")
    employment_type: str | None = Field(
        default=None, description="Employment type (e.g. Full-time, Internship, Trainee)."
    )
    experience_min: float | None = Field(default=None, ge=0.0, description="Minimum years of experience required.")
    experience_max: float | None = Field(default=None, ge=0.0, description="Maximum years of experience required.")
    graduation_year_min: int | None = Field(
        default=None, ge=1990, le=2035, description="Earliest acceptable graduation year."
    )
    graduation_year_max: int | None = Field(
        default=None, ge=1990, le=2035, description="Latest acceptable graduation year."
    )
    description: str | None = Field(default=None, description="Cleaned full job description text.")
    requirements: str | None = Field(default=None, description="Extracted requirements or qualifications.")
    skills: list[str] = Field(default_factory=list, description="Extracted skill keywords.")
    application_url: str | None = Field(default=None, description="Direct link to apply.")
    source: str = Field(..., min_length=1, description="Source provenance.")
    status: JobStatus = Field(default=JobStatus.ACTIVE, description="Listing status.")
    first_seen: str = Field(..., description="ISO-8601 timestamp when first ingested.")
    last_seen: str = Field(..., description="ISO-8601 timestamp when last verified active.")
    fingerprint: str = Field(
        ..., min_length=1, description="Deterministic deduplication fingerprint."
    )
    published_at: str | None = Field(
        default=None, description="ISO-8601 publication timestamp if verified by source."
    )
    posted_at: str | None = Field(
        default=None, description="Explicit posting timestamp if provided."
    )
    discovered_at: str | None = Field(
        default=None, description="Timestamp when first detected by career buddy."
    )
    source_timestamp: str | None = Field(
        default=None, description="Raw timestamp string provided by source."
    )
    freshness_status: str | None = Field(
        default="unknown", description="Freshness category (fresh_0_6_hours, fresh_6_24_hours, recent_1_3_days, older, unknown)."
    )
    freshness_bucket: str | None = Field(
        default="UNKNOWN", description="Granular freshness bucket (<= 1 hour, <= 3 hours, <= 6 hours, <= 12 hours, <= 24 hours, etc)."
    )
    freshness_confidence: str | None = Field(
        default="LOW", description="Timestamp confidence: HIGH, MEDIUM, LOW, UNKNOWN."
    )
    timestamp_source: str | None = Field(
        default="unverified", description="Provenance of timestamp (e.g., official_listing, feed_metadata, unverified)."
    )
    freshness_age_hours: float | None = Field(
        default=None, ge=0.0, description="Calculated age in hours at discovery."
    )
    region: str | None = Field(
        default="india", description="Market classification: india, overseas, global."
    )
    city: str | None = Field(
        default=None, description="Specific city if identified."
    )
    workplace_type: str | None = Field(
        default="unknown", description="Workplace arrangement: onsite, hybrid, remote, unknown."
    )
    remote_type: str | None = Field(
        default="unknown", description="Remote classification alias."
    )
    visa_sponsorship: str | None = Field(
        default="unknown", description="Visa sponsorship status if explicitly stated."
    )
    visa_status: str | None = Field(
        default="unknown", description="Visa category alias."
    )
    sponsorship_confidence: str | None = Field(
        default="LOW", description="Sponsorship confidence: HIGH, MEDIUM, LOW."
    )
    source_name: str | None = Field(
        default=None, description="Adapter / source identifier."
    )
    source_type: str | None = Field(
        default="career_pages", description="Source classification: rss, api, public_feed, career_pages, manual."
    )
    source_job_id: str | None = Field(
        default=None, description="External job identifier from source."
    )
    canonical_url: str | None = Field(
        default=None, description="Normalized canonical link."
    )
    source_references: list[str] = Field(
        default_factory=list, description="All sources that reported this job posting."
    )
    first_notified_at: str | None = Field(
        default=None, description="Timestamp of first proposal notification."
    )
    last_notified_at: str | None = Field(
        default=None, description="Timestamp of most recent proposal notification."
    )
    notification_count: int = Field(
        default=0, ge=0, description="Number of times candidate was alerted."
    )
    priority_score: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Explainable 8-dimensional priority score (0-100)."
    )
    priority_category: str = Field(
        default="LOW", description="Classification: CRITICAL, HIGH, MEDIUM, LOW, EXPIRED_STALE."
    )
    is_watchlist: bool = Field(
        default=False, description="Whether company is on candidate watchlist."
    )




class ApplicationRecord(BaseModel):
    """Human-in-the-loop application tracking record."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: int | None = None
    job_id: int = Field(..., description="Foreign key to normalized_jobs.id.")
    status: ApplicationStatus = Field(
        default=ApplicationStatus.DISCOVERED,
        description="Current application pipeline status.",
    )
    notes: str | None = Field(default=None, description="Candidate review notes.")
    tailored_resume_path: str | None = Field(
        default=None, description="File path to approved tailored resume."
    )
    cover_letter_path: str | None = Field(
        default=None, description="File path to approved cover letter."
    )
    applied_at: str | None = Field(
        default=None, description="ISO-8601 timestamp when candidate submitted application manually."
    )
    created_at: str = Field(..., description="ISO-8601 creation timestamp.")
    updated_at: str = Field(..., description="ISO-8601 last update timestamp.")


class ApplicationEvent(BaseModel):
    """Detailed audit trail event recording actions and submissions."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: int | None = None
    application_id: int = Field(..., description="Foreign key to applications.id.")
    job_id: int = Field(..., description="Foreign key to normalized_jobs.id.")
    event_type: ApplicationEventType = Field(..., description="Type of action or transition recorded.")
    company: str = Field(..., min_length=1, description="Target company name.")
    role_title: str = Field(..., min_length=1, description="Target role title.")
    location: str | None = Field(default=None, description="Job location.")
    source: str = Field(..., min_length=1, description="Origin source.")
    official_application_url: str | None = Field(
        default=None, description="Official destination URL where application was submitted."
    )
    timestamp: str = Field(..., description="ISO-8601 UTC timestamp of the action.")
    resume_version: str | None = Field(
        default=None, description="Identifier / filename of the tailored resume version used."
    )
    cover_letter_version: str | None = Field(
        default=None, description="Identifier / filename of the cover letter version used."
    )
    application_status: ApplicationStatus = Field(
        ..., description="Resulting application lifecycle status."
    )
    reference_id: str | None = Field(
        default=None, description="Official portal application or confirmation reference ID."
    )
    submission_evidence: str | None = Field(
        default=None, description="Evidence proof (e.g., screenshot path, email text snippet, confirmation link)."
    )
    notes: str | None = Field(default=None, description="Audit or error notes.")


class NotificationRecord(BaseModel):
    """User notification generated in response to application lifecycle events."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: int | None = None
    application_id: int | None = Field(default=None, description="Linked application ID if applicable.")
    job_id: int | None = Field(default=None, description="Linked job ID if applicable.")
    notification_type: NotificationType = Field(..., description="Type of notification.")
    title: str = Field(..., min_length=1, description="Notification header.")
    message: str = Field(..., min_length=1, description="Notification body content.")
    created_at: str = Field(..., description="ISO-8601 creation timestamp.")
    is_read: bool = Field(default=False, description="Read/unread status.")


class DeliveryStatus(str, Enum):
    """Lifecycle status of email notification delivery."""

    PROPOSED = "PROPOSED"
    QUEUED = "QUEUED"
    SENDING = "SENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    SUPPRESSED = "SUPPRESSED"


class EmailDeliveryRecord(BaseModel):
    """Audit record for email notification deliveries."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: int | None = None
    notification_id: int | None = Field(default=None, description="Linked proposed_schedule_notifications id.")
    job_id: int | None = Field(default=None, description="Linked normalized_jobs id.")
    application_id: int | None = Field(default=None, description="Linked applications id.")
    recipient: str = Field(..., min_length=1, description="Target recipient email address.")
    priority: str = Field(..., description="CRITICAL, HIGH, APPLY, WATCH, DIGEST, etc.")
    subject: str = Field(..., min_length=1, description="Subject line of email.")
    delivery_status: DeliveryStatus = Field(default=DeliveryStatus.PROPOSED, description="Delivery status.")
    provider: str = Field(..., description="Provider identifier (smtp, console, sendgrid, mock).")
    provider_message_id: str | None = Field(default=None, description="Message ID returned by provider.")
    attempt_count: int = Field(default=0, ge=0, description="Delivery attempt count.")
    created_at: str = Field(..., description="ISO-8601 creation timestamp.")
    queued_at: str | None = None
    sent_at: str | None = None
    failed_at: str | None = None
    last_error: str | None = None
    fingerprint: str | None = Field(default=None, description="Job / digest fingerprint for deduplication.")


# -------------------------------------------------------------------------
# Career Knowledge Base Models
# -------------------------------------------------------------------------
class InterviewSession(BaseModel):
    """Historical or mock interview interaction record."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: int | None = None
    company: str = Field(..., min_length=1, description="Company interviewed with.")
    role: str = Field(..., min_length=1, description="Role interviewed for.")
    date: str = Field(..., description="ISO-8601 date of the interview.")
    round: str = Field(..., min_length=1, description="Round name (e.g., Technical 1, Managerial, HR).")
    outcome: str | None = Field(default=None, description="Outcome if known (e.g., passed, rejected, offer).")
    notes: str | None = Field(default=None, description="Candidate impression and session reflections.")
    created_at: str = Field(..., description="ISO-8601 record creation timestamp.")


class InterviewQuestion(BaseModel):
    """Specific question asked during interviews, mocks, or study discussions."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: int | None = None
    session_id: int | None = Field(default=None, description="FK to interview_sessions if applicable.")
    job_id: int | None = Field(default=None, description="FK to normalized_jobs if linked to a specific job.")
    company: str | None = Field(default=None, description="Associated company.")
    role: str | None = Field(default=None, description="Associated role title.")
    question: str = Field(..., min_length=1, description="The interview question text.")
    category: str = Field(default="technical", description="Category (e.g., technical, hr, project_deep_dive).")
    topic: str = Field(..., min_length=1, description="Core topic (e.g., SystemVerilog OOP, UVM Scoreboard).")
    user_answer: str | None = Field(default=None, description="User's original response.")
    expected_answer: str | None = Field(default=None, description="Ideal or reference answer.")
    feedback: str | None = Field(default=None, description="Interviewer or self feedback.")
    was_correct: bool | None = Field(default=None, description="Evaluation: True if answered correctly, False if missed.")
    difficulty: str | None = Field(default=None, description="Difficulty rating (easy, medium, hard).")
    source: str = Field(..., min_length=1, description="Origin provenance (e.g., 'Synopsys Interview', 'Mock Session').")
    verified: bool = Field(default=False, description="Whether answer/explanation is verified factual knowledge.")
    times_asked: int = Field(default=1, ge=1, description="Frequency of this question across interviews.")
    created_at: str = Field(..., description="ISO-8601 record creation timestamp.")


class WeakArea(BaseModel):
    """Identified candidate technical or behavioral weak area requiring focused practice."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: int | None = None
    topic: str = Field(..., min_length=1, description="Skill or conceptual topic (e.g., Clock Domain Crossing).")
    description: str = Field(..., min_length=1, description="Description of the gap or misunderstanding.")
    evidence_source: str | None = Field(default=None, description="Source where weak area was identified.")
    severity: str = Field(default="medium", description="Severity classification (low, medium, high, critical).")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Self-assessed confidence level (0.0 to 1.0).")
    last_reviewed: str | None = Field(default=None, description="ISO-8601 timestamp of last review session.")
    review_count: int = Field(default=0, ge=0, description="Number of times this weak area has been revised.")
    resolved: bool = Field(default=False, description="True if marked mastered/resolved.")
    created_at: str = Field(..., description="ISO-8601 record creation timestamp.")


class PreparationSession(BaseModel):
    """Focused study or mock practice session."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: int | None = None
    job_id: int | None = Field(default=None, description="FK to normalized_jobs if targeted to a specific job.")
    date: str = Field(..., description="ISO-8601 date of the prep session.")
    topics: list[str] = Field(default_factory=list, description="List of topics studied.")
    questions_attempted: int = Field(default=0, ge=0, description="Count of practice questions attempted.")
    performance_summary: str | None = Field(default=None, description="Summary notes on session performance.")
    notes: str | None = Field(default=None, description="Candidate preparation notes.")
    created_at: str = Field(..., description="ISO-8601 record creation timestamp.")


class KnowledgeItem(BaseModel):
    """Concept summary, verified reference explanation, or core VLSI rule."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: int | None = None
    topic: str = Field(..., min_length=1, description="Topic name (e.g., UVM Phase Mechanism).")
    concept: str = Field(..., min_length=1, description="Concept title or theorem.")
    explanation: str = Field(..., min_length=1, description="Detailed explanation/solution notes.")
    source: str = Field(..., min_length=1, description="Authoritative reference source.")
    verified: bool = Field(default=False, description="Whether explanation has been verified.")
    related_question_ids: list[int] = Field(default_factory=list, description="IDs of linked InterviewQuestion records.")
    created_at: str = Field(..., description="ISO-8601 record creation timestamp.")


# -------------------------------------------------------------------------
# Adaptive Assessment & Preparation Schedule Models
# -------------------------------------------------------------------------
class AssessmentType(str, Enum):
    """Types of adaptive mock assessments."""

    TIMED_MOCK = "timed_mock"
    PRE_INTERVIEW = "pre_interview"
    REMEDIATION = "remediation"
    TOPIC_DRILL = "topic_drill"


class AssessmentStatus(str, Enum):
    """Lifecycle status of an assessment."""

    CREATED = "created"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class MockQuestionItem(BaseModel):
    """Question instance within an adaptive assessment."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question_id: int = Field(..., description="FK to interview_questions.id.")
    question: str = Field(..., min_length=1, description="Question text.")
    topic: str = Field(..., min_length=1, description="Subject topic.")
    difficulty: str | None = Field(default=None, description="Question difficulty.")
    expected_answer: str | None = Field(default=None, description="Reference correct answer.")
    user_answer: str | None = Field(default=None, description="Candidate response.")
    was_correct: bool | None = Field(default=None, description="Scoring evaluation result.")
    time_spent_seconds: int | None = Field(default=None, ge=0, description="Time taken on this question.")
    feedback: str | None = Field(default=None, description="Evaluation commentary or corrections.")


class AssessmentRecord(BaseModel):
    """Complete record of a timed mock test, pre-interview drill, or remediation test."""

    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    job_id: int | None = Field(default=None, description="FK to normalized_jobs if linked.")
    company: str | None = Field(default=None, description="Target company.")
    role: str | None = Field(default=None, description="Target role.")
    assessment_type: AssessmentType = Field(..., description="Type of assessment.")
    title: str = Field(..., min_length=1, description="Test title.")
    time_limit_minutes: int = Field(default=45, ge=1, description="Allocated time limit.")
    questions: list[MockQuestionItem] = Field(default_factory=list, description="Question items.")
    status: AssessmentStatus = Field(default=AssessmentStatus.CREATED, description="Execution status.")
    score: float | None = Field(default=None, ge=0.0, le=100.0, description="Overall score percentage.")
    total_questions: int = Field(default=0, ge=0, description="Total questions count.")
    correct_count: int = Field(default=0, ge=0, description="Correct questions count.")
    incorrect_count: int = Field(default=0, ge=0, description="Incorrect questions count.")
    topic_breakdown: dict[str, dict[str, int | float]] = Field(
        default_factory=dict, description="Performance breakdown per topic."
    )
    created_at: str = Field(..., description="ISO-8601 creation timestamp.")
    completed_at: str | None = Field(default=None, description="ISO-8601 completion timestamp.")


class ReadinessAssessment(BaseModel):
    """Overall candidate interview readiness evaluation for a target job."""

    model_config = ConfigDict(extra="forbid")

    job_id: int
    company: str
    title: str
    overall_readiness_score: float = Field(..., ge=0.0, le=100.0)
    readiness_level: str = Field(..., description="'High Readiness', 'Moderate Readiness', 'Needs Preparation'")
    mastered_topics: list[str] = Field(default_factory=list)
    weak_topics: list[str] = Field(default_factory=list)
    topic_scores: dict[str, float] = Field(default_factory=dict)
    recommended_action: str
    generated_at: str


class ScheduleMilestone(BaseModel):
    """Specific milestone task in a preparation schedule."""

    model_config = ConfigDict(extra="forbid")

    day_offset: int = Field(..., ge=0, description="Day number (0 = today).")
    date: str = Field(..., description="ISO-8601 target date.")
    title: str = Field(..., min_length=1, description="Milestone title.")
    topics: list[str] = Field(default_factory=list, description="Focus topics.")
    action_type: str = Field(..., description="'study_review', 'timed_mock', 'remediation', 'final_pre_interview'")
    estimated_minutes: int = Field(default=45, ge=15, description="Estimated duration in minutes.")
    requires_user_approval: bool = Field(default=True, description="Human approval gate.")
    approved: bool = Field(default=False, description="Whether milestone action is approved.")
    completed: bool = Field(default=False, description="Whether milestone task has been finished.")


class PreparationSchedule(BaseModel):
    """Multi-day preparation schedule with explicit user approval gates."""

    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    job_id: int
    company: str
    title: str
    target_interview_date: str | None = None
    milestones: list[ScheduleMilestone] = Field(default_factory=list)
    created_at: str

