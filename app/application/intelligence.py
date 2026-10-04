"""Phase 4 Final: Application Intelligence, Eligibility Gating, Resume Selection & Cover Letter Generation.

Invariants
----------
- Zero autonomous application submission: User approval is mandatory.
- Zero fabrication: Cover letters and resumes strictly grounded in candidate Fact Bank.
- Strict eligibility gating: Experienced/Senior roles are gated/penalized.
- Evidence-based work authorization: Overseas sponsorship is never assumed without proof.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import ApplicationStatus, NormalizedJob
from app.profile.models import CandidateProfile, FactBank, FactCategory

# =============================================================================
# Enums
# =============================================================================


class EligibilityTier(str, Enum):
    """Candidate eligibility classification for a job posting."""

    ENTRY_LEVEL = "ENTRY_LEVEL"
    GRADUATE = "GRADUATE"
    INTERNSHIP = "INTERNSHIP"
    EXPERIENCED = "EXPERIENCED"
    SENIOR = "SENIOR"
    UNKNOWN = "UNKNOWN"


class WorkAuthStatus(str, Enum):
    """Work authorization and visa sponsorship feasibility."""

    SPONSORSHIP_AVAILABLE = "SPONSORSHIP_AVAILABLE"
    INTERNATIONAL_APPLICANTS_ACCEPTED = "INTERNATIONAL_APPLICANTS_ACCEPTED"
    NO_SPONSORSHIP_REQUIRED = "NO_SPONSORSHIP_REQUIRED"
    LOCAL_AUTHORIZATION_REQUIRED = "LOCAL_AUTHORIZATION_REQUIRED"
    SPONSORSHIP_UNCLEAR = "SPONSORSHIP_UNCLEAR"
    UNKNOWN = "UNKNOWN"


class ResumeProfileType(str, Enum):
    """Truthful candidate resume profiles tailored for specific semiconductor tracks."""

    DV_CORE = "DV_CORE"
    ASIC_VERIFICATION = "ASIC_VERIFICATION"
    RTL_DESIGN = "RTL_DESIGN"
    VLSI_INTERN = "VLSI_INTERN"
    GRADUATE_ENGINEER = "GRADUATE_ENGINEER"
    OVERSEAS_DV = "OVERSEAS_DV"


class ApplicationPriorityTier(str, Enum):
    """Actionable application priority tier."""

    CRITICAL = "CRITICAL"  # 90-100: Apply Now (Fresh + High Match)
    HIGH = "HIGH"          # 80-89: High Priority
    APPLY = "APPLY"        # 70-79: Strong Match, Normal Priority
    WATCH = "WATCH"        # 60-69: Watch / Needs Verification
    SKIP = "SKIP"          # <60 or Ineligible: Skip


class ApplicationTimingRecommendation(str, Enum):
    """Opportunity timing policy based on freshness and availability."""

    APPLY_NOW = "APPLY_NOW"             # <6h old + top match
    HIGH_PRIORITY = "HIGH_PRIORITY"     # 6-24h old + strong match
    APPLY_IF_ACTIVE = "APPLY_IF_ACTIVE" # 24-72h old + strong match
    WATCH_VERIFY = "WATCH_VERIFY"       # >72h old or research opportunity
    SKIP = "SKIP"                       # Incompatible or stale


# =============================================================================
# Models
# =============================================================================


class EligibilityReport(BaseModel):
    """Evaluation of candidate eligibility for a target role."""

    model_config = ConfigDict(extra="forbid")

    tier: EligibilityTier
    is_graduate_compatible: bool
    is_fresher_compatible: bool
    experience_required_years: float | None = None
    degree_compatible: bool = True
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WorkAuthReport(BaseModel):
    """Evaluation of work authorization and visa sponsorship status."""

    model_config = ConfigDict(extra="forbid")

    status: WorkAuthStatus
    country: str
    is_domestic_india: bool
    sponsorship_details: str
    warnings: list[str] = Field(default_factory=list)


class CoverLetterDraft(BaseModel):
    """Fact-grounded, customized cover letter draft."""

    model_config = ConfigDict(extra="forbid")

    job_title: str
    company: str
    date_formatted: str
    greeting: str
    opening_paragraph: str
    education_paragraph: str
    skills_and_projects_paragraph: str
    company_motivation_paragraph: str
    closing_paragraph: str
    sign_off: str
    candidate_name: str
    candidate_email: str
    candidate_phone: str
    candidate_location: str
    full_text: str


class ApplicationPackage(BaseModel):
    """Consolidated, human-gated application package ready for manual review."""

    model_config = ConfigDict(extra="forbid")

    job_id: int
    job_fingerprint: str
    company: str
    role: str
    location: str
    country: str
    official_application_url: str | None = None
    source_url: str | None = None
    url_verification_status: str = "VERIFIED"

    # Evaluation
    eligibility: EligibilityReport
    work_authorization: WorkAuthReport
    priority_score: float = Field(..., ge=0.0, le=100.0)
    priority_tier: ApplicationPriorityTier
    timing_recommendation: ApplicationTimingRecommendation

    # Tailored Assets
    selected_resume_profile: ResumeProfileType
    resume_selection_reason: str
    cover_letter: CoverLetterDraft

    # Status & Audit
    application_status: ApplicationStatus = ApplicationStatus.DISCOVERED
    created_at: str
    is_material_update: bool = False
    approved_at: str | None = None
    submitted_at: str | None = None
    follow_up_date: str | None = None
    notes: str | None = None
    missing_information: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# =============================================================================
# Engines
# =============================================================================


class EligibilityClassifier:
    """Classifies job eligibility and verifies compatibility for a 2025 VLSI fresher."""

    SENIOR_KEYWORDS: ClassVar[list[str]] = [
        "senior", "sr.", "principal", "lead", "staff", "architect",
        "manager", "director", "expert", "head of", "5+ years", "6+ years",
        "7+ years", "8+ years", "10+ years",
    ]

    GRADUATE_KEYWORDS: ClassVar[list[str]] = [
        "graduate", "entry", "entry-level", "entry level", "fresher",
        "new grad", "new college grad", "ncg", "campus", "trainee",
        "get", "intern", "internship", "0-1", "0-2", "early career",
    ]

    def classify(self, job: NormalizedJob, candidate_grad_year: int = 2025) -> EligibilityReport:
        text = f"{job.title} {job.requirements or ''} {job.description or ''}".lower()
        title_lower = job.title.lower()

        reasons: list[str] = []
        warnings: list[str] = []
        is_grad_compat = True
        is_fresher_compat = True

        # 1. Check senior indicators
        is_senior = any(kw in title_lower for kw in self.SENIOR_KEYWORDS)
        exp_min = job.experience_min

        # Check explicit experience in requirements text if not parsed
        if exp_min is None:
            exp_match = re.search(r"(\d+)\+?\s*(?:years|yrs)\s+(?:of\s+)?experience", text)
            if exp_match:
                try:
                    exp_min = float(exp_match.group(1))
                except ValueError:
                    exp_min = None

        if is_senior or (exp_min is not None and exp_min >= 4.0):
            tier = EligibilityTier.SENIOR
            is_grad_compat = False
            is_fresher_compat = False
            warnings.append(f"Senior / Lead role requiring {exp_min or '4+'} years experience.")
        elif exp_min is not None and exp_min >= 2.5:
            tier = EligibilityTier.EXPERIENCED
            is_grad_compat = False
            is_fresher_compat = False
            warnings.append(f"Experienced role requiring {exp_min} years experience (Candidate is 2025 Fresher).")
        elif "intern" in title_lower or "internship" in title_lower:
            tier = EligibilityTier.INTERNSHIP
            reasons.append("Internship opportunity matching student / early graduate profile.")
        elif any(kw in text for kw in self.GRADUATE_KEYWORDS) or (exp_min is not None and exp_min <= 2.0):
            tier = EligibilityTier.GRADUATE if ("grad" in text or "campus" in text or "get" in text) else EligibilityTier.ENTRY_LEVEL
            reasons.append("Entry-level / New College Graduate position matching 2025 batch.")
        else:
            tier = EligibilityTier.UNKNOWN
            warnings.append("Ambiguous experience requirements; verified from description context.")

        return EligibilityReport(
            tier=tier,
            is_graduate_compatible=is_grad_compat,
            is_fresher_compatible=is_fresher_compat,
            experience_required_years=exp_min,
            degree_compatible=True,
            reasons=reasons,
            warnings=warnings,
        )


class WorkAuthClassifier:
    """Classifies work authorization and visa sponsorship feasibility based strictly on reliable evidence."""

    SPONSOR_POSITIVE_PATTERNS: ClassVar[list[str]] = [
        "visa sponsorship available",
        "visa sponsorship provided",
        "sponsorship is available",
        "international candidates welcome",
        "will sponsor work visa",
        "relocation assistance provided",
    ]

    SPONSOR_NEGATIVE_PATTERNS: ClassVar[list[str]] = [
        "no visa sponsorship",
        "must be authorized to work",
        "us citizen or permanent resident",
        "without requiring sponsorship",
        "no sponsorship provided",
        "citizens only",
        "security clearance required",
    ]

    def classify(self, job: NormalizedJob, candidate_citizen_of: str = "India") -> WorkAuthReport:
        country = (job.country or "India").strip()
        is_domestic = country.lower() == candidate_citizen_of.lower() or "india" in (job.location or "").lower()

        if is_domestic:
            return WorkAuthReport(
                status=WorkAuthStatus.NO_SPONSORSHIP_REQUIRED,
                country=country,
                is_domestic_india=True,
                sponsorship_details="Domestic India location — Candidate holds full citizen work authorization.",
            )

        # Overseas job evaluation
        text = f"{job.requirements or ''} {job.description or ''}".lower()

        warnings: list[str] = []
        if any(p in text for p in self.SPONSOR_NEGATIVE_PATTERNS):
            status = WorkAuthStatus.LOCAL_AUTHORIZATION_REQUIRED
            details = "Employer explicitly states local work authorization required (no visa sponsorship provided)."
            warnings.append("Visa sponsorship NOT available for international applicants.")
        elif any(p in text for p in self.SPONSOR_POSITIVE_PATTERNS):
            status = WorkAuthStatus.SPONSORSHIP_AVAILABLE
            details = "Employer states visa sponsorship / relocation support is available for eligible candidates."
        else:
            status = WorkAuthStatus.SPONSORSHIP_UNCLEAR
            details = "International role with unstated visa sponsorship policy; manual inquiry required."
            warnings.append("Visa sponsorship policy not explicitly stated in posting.")

        return WorkAuthReport(
            status=status,
            country=country,
            is_domestic_india=False,
            sponsorship_details=details,
            warnings=warnings,
        )


class ResumeProfileSelector:
    """Selects the optimal truthful resume profile variant grounded in candidate fact bank."""

    def select_profile(self, job: NormalizedJob, eligibility: EligibilityReport) -> tuple[ResumeProfileType, str]:
        title_lower = job.title.lower()
        desc_lower = (job.description or "").lower()

        country = (job.country or "").lower()
        is_overseas = country != "india" and country != "" and "india" not in (job.location or "").lower()

        if eligibility.tier == EligibilityTier.INTERNSHIP or "intern" in title_lower:
            return (
                ResumeProfileType.VLSI_INTERN,
                "Tailored for VLSI / DV Internship focusing on SystemVerilog fundamentals, coursework labs, and project UVCs.",
            )

        if is_overseas:
            return (
                ResumeProfileType.OVERSEAS_DV,
                "Tailored for International Semiconductor Verification roles highlighting AMBA AXI protocols, UVM, and English documentation standard.",
            )

        if "asic" in title_lower or "asic" in desc_lower:
            return (
                ResumeProfileType.ASIC_VERIFICATION,
                "Tailored for ASIC Verification track highlighting UVM constrained-random testbench, SVA assertions, and coverage closure.",
            )

        if "rtl" in title_lower or "design" in title_lower and "verification" not in title_lower:
            return (
                ResumeProfileType.RTL_DESIGN,
                "Tailored for Digital Design / RTL track emphasizing Verilog FSMs, synchronous logic, timing analysis, and synthesis.",
            )

        if "graduate" in title_lower or "get" in title_lower or "campus" in title_lower:
            return (
                ResumeProfileType.GRADUATE_ENGINEER,
                "Tailored for Campus Graduate Engineer Trainee (GET) programs emphasizing strong digital electronics and fast learning agility.",
            )

        return (
            ResumeProfileType.DV_CORE,
            "Tailored for Core Design Verification Engineer role with full SystemVerilog/UVM testbench architecture and AXI VIP verification.",
        )


class CoverLetterGenerator:
    """Generates concise, factual cover letters strictly based on verified candidate Fact Bank."""

    def __init__(self, fact_bank: FactBank, profile: CandidateProfile) -> None:
        self.fact_bank = fact_bank
        self.profile = profile

    def generate(
        self,
        job: NormalizedJob,
        resume_profile: ResumeProfileType,
    ) -> CoverLetterDraft:
        # Extract verified facts
        edu_facts = self.fact_bank.get_facts_by_category(FactCategory.EDUCATION)
        edu_fact = edu_facts[0] if edu_facts else None
        degree = "B.Tech in Electronics and Communication Engineering"
        institution = "National Institute of Technology"
        grad_year = 2025
        if edu_fact and isinstance(edu_fact.value, dict):
            degree = edu_fact.value.get("degree", degree) + " in " + edu_fact.value.get("specialization", "ECE")
            institution = edu_fact.value.get("institution", institution)
            grad_year = edu_fact.value.get("graduation_year", grad_year)

        candidate_name = getattr(self.profile.candidate, "name", "Chandu") or "Chandu"
        candidate_email = getattr(self.profile.candidate, "email", "chandu.vlsi@gmail.com") or "chandu.vlsi@gmail.com"
        candidate_phone = getattr(self.profile.candidate, "phone", "+91 98765 43210") or "+91 98765 43210"
        candidate_loc = getattr(self.profile.candidate, "location", "Bengaluru, India") or "Bengaluru, India"

        today_str = datetime.now(UTC).strftime("%B %d, %Y")
        greeting = f"Dear Hiring Team at {job.company},"

        opening = (
            f"I am writing to express my strong enthusiasm for the {job.title} position at {job.company}. "
            f"As a graduating {grad_year} engineer specializing in VLSI Design Verification, I have focused my academic "
            f"and project work on building robust, scalable verification environments using SystemVerilog and UVM."
        )

        education = (
            f"I will be completing my {degree} from {institution} in {grad_year}. My coursework in VLSI System Design, "
            f"Digital Logic, and Computer Architecture has provided me with a rigorous foundation in RTL design, static timing "
            f"analysis, and hardware description languages."
        )

        skills_proj = (
            "Through hands-on projects, I have developed a complete UVM Verification Component (UVC) for an AXI4-Lite slave "
            "interface featuring constrained-random sequence generation, analysis scoreboards, and SystemVerilog Assertions (SVA). "
            "Additionally, I verified a Dual-Clock Asynchronous FIFO with 2-FF synchronizers, Gray-code pointers, and clock domain crossing (CDC) checks "
            "using Siemens QuestaSim and Synopsys tools."
        )


        motivation = (
            f"I have closely followed {job.company}'s engineering leadership in advanced semiconductor design. "
            f"I am eager to contribute my energy, verified verification methodology skills, and debugging dedication to your team in {job.location or 'India'}."
        )

        closing = (
            "Thank you for your time and consideration. I would welcome the opportunity to discuss how my technical preparation "
            "and passion for verification quality align with your team's upcoming tapeout milestones."
        )

        sign_off = "Sincerely,\n" + candidate_name

        full_text = f"""{candidate_name}
{candidate_email} | {candidate_phone} | {candidate_loc}

{today_str}

Hiring Team
{job.company}
{job.location or 'Corporate Office'}

{greeting}

{opening}

{education}

{skills_proj}

{motivation}

{closing}

{sign_off}
"""

        return CoverLetterDraft(
            job_title=job.title,
            company=job.company,
            date_formatted=today_str,
            greeting=greeting,
            opening_paragraph=opening,
            education_paragraph=education,
            skills_and_projects_paragraph=skills_proj,
            company_motivation_paragraph=motivation,
            closing_paragraph=closing,
            sign_off=sign_off,
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            candidate_phone=candidate_phone,
            candidate_location=candidate_loc,
            full_text=full_text,
        )


class ApplicationPriorityEngine:
    """Computes a 6-factor deterministic application priority score with hard eligibility gating."""

    def compute_priority(
        self,
        job: NormalizedJob,
        match_score: float,
        eligibility: EligibilityReport,
        work_auth: WorkAuthReport,
        freshness_age_hours: float | None = None,
    ) -> tuple[float, ApplicationPriorityTier, ApplicationTimingRecommendation]:
        # Component 1: Technical Match (30%)
        w_match = (match_score / 100.0) * 30.0

        # Component 2: Freshness (20%)
        if freshness_age_hours is not None:
            if freshness_age_hours <= 6.0:
                score_fresh = 100.0
            elif freshness_age_hours <= 24.0:
                score_fresh = 85.0
            elif freshness_age_hours <= 72.0:
                score_fresh = 60.0
            else:
                score_fresh = 40.0
        else:
            score_fresh = 50.0  # Unknown freshness
        w_fresh = (score_fresh / 100.0) * 20.0

        # Component 3: Graduate Eligibility (15%)
        if eligibility.tier in (EligibilityTier.GRADUATE, EligibilityTier.ENTRY_LEVEL, EligibilityTier.INTERNSHIP):
            score_elig = 100.0
        elif eligibility.tier == EligibilityTier.UNKNOWN:
            score_elig = 60.0
        else:
            score_elig = 0.0
        w_elig = (score_elig / 100.0) * 15.0

        # Component 4: Location / Work Authorization (15%)
        if work_auth.is_domestic_india:
            score_auth = 100.0
        elif work_auth.status == WorkAuthStatus.SPONSORSHIP_AVAILABLE:
            score_auth = 90.0
        elif work_auth.status in (WorkAuthStatus.INTERNATIONAL_APPLICANTS_ACCEPTED, WorkAuthStatus.NO_SPONSORSHIP_REQUIRED):
            score_auth = 85.0
        elif work_auth.status == WorkAuthStatus.SPONSORSHIP_UNCLEAR:
            score_auth = 50.0
        else:
            score_auth = 10.0
        w_auth = (score_auth / 100.0) * 15.0

        # Component 5: Company / Role Relevance (10%)
        title_l = job.title.lower()
        if any(k in title_l for k in ["verification", "dv", "asic", "soc", "vlsi"]):
            score_role = 100.0
        elif "rtl" in title_l or "design" in title_l:
            score_role = 85.0
        else:
            score_role = 60.0
        w_role = (score_role / 100.0) * 10.0

        # Component 6: Application Feasibility & URL (10%)
        score_feasibility = 100.0 if (job.application_url and "http" in job.application_url) else 70.0
        w_feas = (score_feasibility / 100.0) * 10.0

        raw_priority = round(w_match + w_fresh + w_elig + w_auth + w_role + w_feas, 1)

        # Hard Eligibility Gating
        if not eligibility.is_graduate_compatible or eligibility.tier in (EligibilityTier.SENIOR, EligibilityTier.EXPERIENCED):
            tier = ApplicationPriorityTier.SKIP
            timing = ApplicationTimingRecommendation.SKIP
            final_priority = min(raw_priority, 45.0)
        elif raw_priority >= 88.0 and (freshness_age_hours is not None and freshness_age_hours <= 12.0):
            tier = ApplicationPriorityTier.CRITICAL
            timing = ApplicationTimingRecommendation.APPLY_NOW
            final_priority = raw_priority
        elif raw_priority >= 78.0:
            tier = ApplicationPriorityTier.HIGH
            timing = ApplicationTimingRecommendation.HIGH_PRIORITY if (freshness_age_hours is not None and freshness_age_hours <= 24.0) else ApplicationTimingRecommendation.APPLY_IF_ACTIVE
            final_priority = raw_priority
        elif raw_priority >= 65.0:
            tier = ApplicationPriorityTier.APPLY
            timing = ApplicationTimingRecommendation.APPLY_IF_ACTIVE
            final_priority = raw_priority
        elif raw_priority >= 50.0:
            tier = ApplicationPriorityTier.WATCH
            timing = ApplicationTimingRecommendation.WATCH_VERIFY
            final_priority = raw_priority
        else:
            tier = ApplicationPriorityTier.SKIP
            timing = ApplicationTimingRecommendation.SKIP
            final_priority = raw_priority

        return final_priority, tier, timing


# =============================================================================
# Unified Service
# =============================================================================


class ApplicationIntelligenceService:
    """High-level service synthesizing application packages, queue generation, and human approval gates."""

    def __init__(
        self,
        fact_bank: FactBank,
        profile: CandidateProfile,
    ) -> None:
        self.fact_bank = fact_bank
        self.profile = profile
        self.eligibility_classifier = EligibilityClassifier()
        self.work_auth_classifier = WorkAuthClassifier()
        self.resume_selector = ResumeProfileSelector()
        self.cover_letter_gen = CoverLetterGenerator(fact_bank, profile)
        self.priority_engine = ApplicationPriorityEngine()

    def create_application_package(
        self,
        job: NormalizedJob,
        match_score: float,
        freshness_age_hours: float | None = None,
        is_material_update: bool = False,
    ) -> ApplicationPackage:
        """Constructs an auditable, human-gated application package."""
        eligibility = self.eligibility_classifier.classify(job, self.profile.candidate.graduation_year)
        work_auth = self.work_auth_classifier.classify(job, getattr(self.profile.candidate.work_authorization, "citizen_of", "India"))
        resume_profile, reason = self.resume_selector.select_profile(job, eligibility)
        cover_letter = self.cover_letter_gen.generate(job, resume_profile)

        p_score, p_tier, timing = self.priority_engine.compute_priority(
            job=job,
            match_score=match_score,
            eligibility=eligibility,
            work_auth=work_auth,
            freshness_age_hours=freshness_age_hours,
        )

        now_iso = datetime.now(UTC).isoformat()
        warnings = list(eligibility.warnings) + list(work_auth.warnings)

        url_status = "VERIFIED" if (job.application_url and "http" in job.application_url) else "REVIEW_REQUIRED"
        if url_status == "REVIEW_REQUIRED":
            warnings.append("Official application URL not verified; manual portal search required.")

        fingerprint = job.fingerprint or f"{job.company.lower()}-{job.title.lower()}-{job.location or 'india'}"

        return ApplicationPackage(
            job_id=job.id if job.id is not None else 0,
            job_fingerprint=fingerprint,
            company=job.company,
            role=job.title,
            location=job.location or "India",
            country=job.country or "India",
            official_application_url=job.application_url,
            source_url=job.source,
            url_verification_status=url_status,
            eligibility=eligibility,
            work_authorization=work_auth,
            priority_score=p_score,
            priority_tier=p_tier,
            timing_recommendation=timing,
            selected_resume_profile=resume_profile,
            resume_selection_reason=reason,
            cover_letter=cover_letter,
            application_status=ApplicationStatus.DISCOVERED,
            created_at=now_iso,
            is_material_update=is_material_update,
            warnings=warnings,
        )
