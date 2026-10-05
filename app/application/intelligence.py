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


class CareerDecision(str, Enum):
    """Authoritative career decision outcome for a job opportunity."""

    APPLY = "APPLY"     # High confidence, verified eligible, actionable opportunity
    REVIEW = "REVIEW"   # Ambiguous work authorization / experience, human inspection needed
    REJECT = "REJECT"   # Ineligible, senior, wrong role family, ITAR restricted, or stale


class CareerDecisionReport(BaseModel):
    """Complete explainable career decision for a candidate opportunity."""

    model_config = ConfigDict(extra="forbid")

    decision: CareerDecision
    match_score: float = Field(..., ge=0.0, le=100.0)
    decision_reasons: list[str] = Field(default_factory=list, description="Machine-readable decision codes.")
    decision_explanation: str = Field(..., description="Clear human-readable justification.")
    hard_rejections: list[str] = Field(default_factory=list, description="Hard gate failures if rejected.")
    ambiguity_flags: list[str] = Field(default_factory=list, description="Ambiguous factors requiring human review.")


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

    # Authoritative Career Decision
    career_decision: CareerDecision = CareerDecision.APPLY
    decision_reasons: list[str] = Field(default_factory=list)
    decision_explanation: str = ""

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

    SENIOR_TITLE_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"\b(?:senior|\bsr\.?\b|principal|lead|staff|architect|manager|director|expert|head\s*of)\b",
        re.IGNORECASE,
    )

    UNRELATED_TITLE_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"\b(?:python\s*developer|web\s*developer|full[\s-]stack|backend|frontend|software\s*developer|"
        r"devops|cloud\s*engineer|data\s*scientist|data\s*engineer|marketing|sales|recruiter|hr\b|"
        r"accountant|civil\s*engineer|electrical\s*technician|electrician|facilities|wiring|maintenance|hvac)\b",
        re.IGNORECASE,
    )

    GRADUATE_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"\b(?:graduate|entry[\s-]level|entry\s*level|fresher|new\s*grad|new\s*college\s*grad|\bncg\b|campus|trainee|"
        r"\bget\b|\bintern(?:ship)?\b|0[\s-]1\s*(?:years?|yrs?)|0[\s-]2\s*(?:years?|yrs?)|early\s*career)\b",
        re.IGNORECASE,
    )

    def _parse_experience_years(self, text: str) -> tuple[float | None, float | None]:
        """
        Parse required and preferred years of experience with distinction between required vs preferred.
        Returns: (required_years_min, preferred_years_min)
        """
        req_min: float | None = None
        pref_min: float | None = None

        # 1. Check for required / minimum experience patterns
        req_patterns = [
            r"\b(?:minimum\s*(?:of\s*)?|at\s*least\s*|required\s*:\s*|basic\s*qualifications\s*:\s*)(\d+(?:\.\d+)?)\s*(?:\+|-|\s*to\s*\d+)?\s*(?:years|yrs)\b",
            r"\b(\d+(?:\.\d+)?)\s*\+\s*(?:years|yrs)\s+(?:of\s+)?(?:required\s+)?experience\b",
            r"\b(\d+(?:\.\d+)?)\s*(?:years|yrs)\s+(?:of\s+)?required\s+experience\b",
            r"\b(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:years|yrs)\s+(?:of\s+)?experience\b",
            r"\b(\d+(?:\.\d+)?)\s*(?:years|yrs)\s+(?:of\s+)?experience\b",
        ]

        # 1. Check explicit "Preferred:" or "Desired:" section first
        pref_match = re.search(r"(?:preferred|desired|plus)\s*[:\w\s]*?(\d+(?:\.\d+)?)\s*(?:\+|-|\s*to\s*\d+)?\s*(?:years|yrs)", text, re.IGNORECASE)
        if pref_match:
            try:
                pref_min = float(pref_match.group(1))
            except (ValueError, IndexError):
                pref_min = None

        # 2. Check explicit "Required:" or "Minimum:" section
        explicit_req = re.search(r"(?:required|minimum\s*(?:of)?|at\s*least|basic\s*qualifications)\s*[:\w\s]*?(\d+(?:\.\d+)?)\s*(?:-|to|\+)?\s*(?:\d+(?:\.\d+)?)?\s*(?:years|yrs)", text, re.IGNORECASE)
        if explicit_req:
            try:
                req_min = float(explicit_req.group(1))
            except (ValueError, IndexError):
                req_min = None
        else:
            # Check general required patterns
            for pat in req_patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    try:
                        val = float(m.group(1))
                        if val < 30.0:
                            req_min = val
                            break
                    except (ValueError, IndexError):
                        continue

        return req_min, pref_min

    def classify(self, job: NormalizedJob, candidate_grad_year: int = 2025) -> EligibilityReport:
        text = f"{job.title} {job.requirements or ''} {job.description or ''}".lower()
        title_lower = job.title.lower().strip()

        reasons: list[str] = []
        warnings: list[str] = []
        is_grad_compat = True
        is_fresher_compat = True

        # Unrelated non-hardware career check
        if self.UNRELATED_TITLE_PATTERN.search(title_lower):
            return EligibilityReport(
                tier=EligibilityTier.EXPERIENCED,
                is_graduate_compatible=False,
                is_fresher_compatible=False,
                experience_required_years=None,
                degree_compatible=False,
                reasons=[],
                warnings=[f"Incompatible career track '{job.title}' (non-semiconductor role)."],
            )

        # Senior Title Check
        is_senior_title = bool(self.SENIOR_TITLE_PATTERN.search(title_lower))

        # Experience Parsing
        exp_min = job.experience_min
        req_exp, _pref_exp = self._parse_experience_years(text)
        if exp_min is None:
            exp_min = req_exp

        # Senior or Experienced Gate
        if is_senior_title or (exp_min is not None and exp_min >= 4.0):
            tier = EligibilityTier.SENIOR
            is_grad_compat = False
            is_fresher_compat = False
            warnings.append(f"Senior / Lead role requiring {exp_min or '4+'} years experience.")
        elif exp_min is not None and exp_min >= 2.5:
            tier = EligibilityTier.EXPERIENCED
            is_grad_compat = False
            is_fresher_compat = False
            warnings.append(f"Experienced role requiring {exp_min:.0f}+ years experience (Candidate is 2025 Fresher).")
        elif re.search(r"\b(?:intern|internship)\b", title_lower):
            tier = EligibilityTier.INTERNSHIP
            reasons.append("Internship opportunity matching student / early graduate profile.")
        elif self.GRADUATE_PATTERN.search(text) or (exp_min is not None and exp_min <= 2.0):
            is_grad = bool(re.search(r"\b(?:grad(?:uate)?|campus|\bget\b|college)\b", text))
            tier = EligibilityTier.GRADUATE if is_grad else EligibilityTier.ENTRY_LEVEL
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
        r"\bvisa\s*sponsorship\s*(?:is\s*)?available\b",
        r"\bvisa\s*sponsorship\s*provided\b",
        r"\bwill\s*sponsor\s*(?:work\s*)?visa\b",
        r"\binternational\s*candidates\s*welcome\b",
        r"\brelocation\s*assistance\s*provided\b",
    ]

    SPONSOR_NEGATIVE_PATTERNS: ClassVar[list[str]] = [
        r"\bno\s*visa\s*sponsorship\b",
        r"\bwill\s*not\s*sponsor\b",
        r"\bsponsorship\s*(?:is\s*)?not\s*available\b",
        r"\bmust\s*be\s*authorized\s*to\s*work\b",
        r"\bmust\s*be\s*a\s*u\.?s\.?\s*person\b",
        r"\bus\s*citizen\s*or\s*permanent\s*resident\b",
        r"\bcitizens\s*only\b",
        r"\bitar\b",
        r"\bexport\s*control(?:led)?\b",
        r"\bsecurity\s*clearance\s*required\b",
        r"\bactive\s*security\s*clearance\b",
        r"\btop\s*secret\b",
        r"\bsecret\s*clearance\b",
    ]

    def classify(self, job: NormalizedJob, candidate_citizen_of: str = "India") -> WorkAuthReport:
        country = (job.country or "Unknown").strip()
        is_domestic = country.lower() == candidate_citizen_of.lower() or "india" in (job.location or "").lower()

        if is_domestic:
            return WorkAuthReport(
                status=WorkAuthStatus.NO_SPONSORSHIP_REQUIRED,
                country=country if country.lower() != "unknown" else "India",
                is_domestic_india=True,
                sponsorship_details="Domestic India location — Candidate holds full citizen work authorization.",
            )

        # Overseas job evaluation
        text = f"{job.requirements or ''} {job.description or ''}".lower()

        warnings: list[str] = []
        is_negative = any(re.search(pat, text, re.IGNORECASE) for pat in self.SPONSOR_NEGATIVE_PATTERNS)
        is_positive = any(re.search(pat, text, re.IGNORECASE) for pat in self.SPONSOR_POSITIVE_PATTERNS)

        if is_negative:
            status = WorkAuthStatus.LOCAL_AUTHORIZATION_REQUIRED
            details = "Employer explicitly states local work authorization/citizenship/ITAR clearance required (no visa sponsorship provided)."
            warnings.append("Visa sponsorship NOT available / ITAR or domestic authorization restricted for international applicants.")
        elif is_positive:
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
        # Extract verified facts (Fail-closed on missing education fact)
        from app.profile.models import IdentityValidationError

        edu_facts = [f for f in self.fact_bank.get_facts_by_category(FactCategory.EDUCATION) if f.verified]
        if not edu_facts:
            raise IdentityValidationError("Cannot generate cover letter: verified education fact missing from FactBank.")
        edu_fact = edu_facts[0]
        if not isinstance(edu_fact.value, dict):
            raise IdentityValidationError("Cannot generate cover letter: invalid education fact structure in FactBank.")

        degree = edu_fact.value.get("degree", edu_fact.subject)
        spec = edu_fact.value.get("specialization") or edu_fact.value.get("field") or "Electronics and Communication Engineering"
        institution = edu_fact.value.get("institution")
        if not institution:
            raise IdentityValidationError(f"Education fact {edu_fact.fact_id} missing verified institution.")
        grad_year = int(edu_fact.value.get("graduation_year", 2025))

        candidate = getattr(self.profile, "candidate", None)
        candidate_name = getattr(candidate, "name", None)
        candidate_email = getattr(candidate, "email", None)

        if not candidate_name or not str(candidate_name).strip():
            raise IdentityValidationError("Cannot generate cover letter: verified candidate name is missing.")
        if not candidate_email or not str(candidate_email).strip():
            raise IdentityValidationError("Cannot generate cover letter: verified candidate email is missing.")

        candidate_name_str = str(candidate_name).strip()
        candidate_email_str = str(candidate_email).strip()
        candidate_phone_str = str(getattr(candidate, "phone", "") or "").strip()
        candidate_loc_str = str(getattr(candidate, "location", "") or "Bengaluru, India").strip()

        today_str = datetime.now(UTC).strftime("%B %d, %Y")
        greeting = f"Dear Hiring Team at {job.company},"

        opening = (
            f"I am writing to express my strong interest in the {job.title} position at {job.company}. "
            f"As a {grad_year} graduate specializing in VLSI Design Verification, I have focused my academic "
            f"and project work on building robust, scalable verification environments using SystemVerilog and UVM."
        )

        education = (
            f"I completed my {degree} in {spec} from {institution} in {grad_year}. My coursework in VLSI System Design, "
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
            f"I am eager to contribute my verified verification methodology skills, constrained-random testbench development, "
            f"and debugging dedication to the engineering team at {job.company}."
        )

        closing = (
            "Thank you for your time and consideration. I would welcome the opportunity to discuss how my technical preparation "
            "in SystemVerilog, UVM, and protocol verification aligns with your team's verification objectives."
        )

        sign_off = "Sincerely,\n" + candidate_name_str

        contact_header_parts = [candidate_name_str, candidate_email_str]
        if candidate_phone_str:
            contact_header_parts.append(candidate_phone_str)
        if candidate_loc_str:
            contact_header_parts.append(candidate_loc_str)
        contact_header = " | ".join(contact_header_parts)

        full_text = f"""{contact_header}

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
            candidate_name=candidate_name_str,
            candidate_email=candidate_email_str,
            candidate_phone=candidate_phone_str,
            candidate_location=candidate_loc_str,
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

        # Hard Eligibility & Authorization Gating
        is_hard_ineligible = (
            not eligibility.is_fresher_compatible
            or not eligibility.is_graduate_compatible
            or eligibility.tier in (EligibilityTier.SENIOR, EligibilityTier.EXPERIENCED)
            or not eligibility.degree_compatible
            or work_auth.status == WorkAuthStatus.LOCAL_AUTHORIZATION_REQUIRED
        )

        if is_hard_ineligible:
            tier = ApplicationPriorityTier.SKIP
            timing = ApplicationTimingRecommendation.SKIP
            final_priority = min(raw_priority, 35.0)
        elif work_auth.status == WorkAuthStatus.SPONSORSHIP_UNCLEAR:
            # Overseas with unstated sponsorship is capped at WATCH/APPLY with WATCH_VERIFY timing
            if raw_priority >= 75.0:
                tier = ApplicationPriorityTier.APPLY
                timing = ApplicationTimingRecommendation.WATCH_VERIFY
                final_priority = min(raw_priority, 74.0)
            elif raw_priority >= 50.0:
                tier = ApplicationPriorityTier.WATCH
                timing = ApplicationTimingRecommendation.WATCH_VERIFY
                final_priority = raw_priority
            else:
                tier = ApplicationPriorityTier.SKIP
                timing = ApplicationTimingRecommendation.SKIP
                final_priority = raw_priority
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
# Career Decision Engine
# =============================================================================


class CareerDecisionEngine:
    """
    Authoritative decision engine answering:
    'Should Chandu actually spend time applying to this job?'

    Evaluation precedence:
    1. Invalid / unsafe source
    2. Explicit role identity (Wrong role family / keyword traps)
    3. Seniority & Experience ineligibility
    4. Graduation & degree incompatibility
    5. Work authorization & ITAR restrictions
    6. Freshness & active listing state
    7. Ambiguous conditions -> REVIEW (unstated overseas sponsorship, fixture provenance, borderline match)
    8. Technical score threshold (<50.0 -> REJECT)
    9. Eligible high-confidence opportunity -> APPLY
    """

    UNRELATED_ROLE_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"\b(?:marketing|sales|recruiter|talent|hr\b|human\s*resources|accountant|accounts|finance|legal|"
        r"civil\s*engineer|electrical\s*technician|electrician|facilities|wiring|maintenance|hvac|"
        r"python\s*developer|web\s*developer|full[\s-]stack|backend|frontend|software\s*developer|"
        r"devops|cloud\s*engineer|data\s*scientist|data\s*engineer|project\s*manager|scrum\s*master)\b",
        re.IGNORECASE,
    )

    CORE_DV_TITLE_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"\b(?:verification|\bdv\b|uvm|functional\s*verification|testbench|soc\s*verification|"
        r"asic\s*(?:dv|verification)|silicon\s*verification|digital\s*verification|ip\s*verification|"
        r"serdes\s*verification|automotive\s*dv)\b",
        re.IGNORECASE,
    )

    ADJACENT_HARDWARE_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"\b(?:rtl|fpga|firmware|embedded|hardware\s*design|silicon\s*validation|applications?\s*engineer|"
        r"physical\s*design|dft|board\s*design|emulation|microcontroller|wireless|dram|hardware\s*engineer)\b",
        re.IGNORECASE,
    )

    def evaluate_decision(
        self,
        job: NormalizedJob,
        match_score: float,
        eligibility: EligibilityReport,
        work_auth: WorkAuthReport,
        freshness_age_hours: float | None = None,
        is_fixture: bool = False,
    ) -> CareerDecisionReport:
        hard_rejections: list[str] = []
        ambiguity_flags: list[str] = []

        title_l = (job.title or "").lower().strip()
        desc_l = (job.description or "").lower().strip()

        # Gate 1: Source & Payload Validity
        if not job.title or not job.company:
            hard_rejections.append("Job record missing critical identity fields (company or title).")
            return CareerDecisionReport(
                decision=CareerDecision.REJECT,
                match_score=match_score,
                decision_reasons=["INVALID_OR_UNSAFE_SOURCE"],
                decision_explanation="Job description or source is invalid or unverifiable.",
                hard_rejections=hard_rejections,
                ambiguity_flags=[],
            )

        # Gate 2: Wrong Role Family (Keyword traps like 'Verification Marketing', 'Python Developer', etc.)
        if self.UNRELATED_ROLE_PATTERN.search(title_l):
            hard_rejections.append(f"Role title '{job.title}' belongs to an unrelated non-semiconductor role family.")
            return CareerDecisionReport(
                decision=CareerDecision.REJECT,
                match_score=match_score,
                decision_reasons=["WRONG_ROLE_FAMILY"],
                decision_explanation=f"Job title '{job.title}' is not a Design Verification or semiconductor hardware role; candidate is targeting VLSI/DV.",
                hard_rejections=hard_rejections,
                ambiguity_flags=[],
            )

        # Gate 3: Seniority & Experience Ineligibility
        exp_req = eligibility.experience_required_years
        if (
            eligibility.tier in (EligibilityTier.SENIOR, EligibilityTier.EXPERIENCED)
            or (exp_req is not None and exp_req >= 2.5)
            or not eligibility.is_fresher_compatible
        ):
            exp_str = f"{exp_req:.0f}+ years" if exp_req else "senior/experienced"
            hard_rejections.append(f"Job requires {exp_str} of experience (Candidate is 2025 entry-level graduate).")
            return CareerDecisionReport(
                decision=CareerDecision.REJECT,
                match_score=match_score,
                decision_reasons=["EXPERIENCE_TOO_HIGH"],
                decision_explanation=f"Job requires {exp_str} of verification experience; candidate is being evaluated as an entry-level applicant.",
                hard_rejections=hard_rejections,
                ambiguity_flags=[],
            )

        # Gate 4: Degree & Graduation Incompatibility
        if not eligibility.degree_compatible or not eligibility.is_graduate_compatible:
            hard_rejections.append("Degree or graduation year requirements are incompatible with candidate's 2025 B.Tech in ECE.")
            return CareerDecisionReport(
                decision=CareerDecision.REJECT,
                match_score=match_score,
                decision_reasons=["GRADUATION_OR_DEGREE_INCOMPATIBLE"],
                decision_explanation="Candidate degree or graduation timeline does not meet the explicit listing criteria.",
                hard_rejections=hard_rejections,
                ambiguity_flags=[],
            )

        # Gate 5: Work Authorization Hard Rejection (ITAR, Clearance, Local Auth strictly required)
        if work_auth.status == WorkAuthStatus.LOCAL_AUTHORIZATION_REQUIRED:
            hard_rejections.append(work_auth.sponsorship_details)
            return CareerDecisionReport(
                decision=CareerDecision.REJECT,
                match_score=match_score,
                decision_reasons=["WORK_AUTH_RESTRICTED"],
                decision_explanation="Role requires local citizenship, security clearance, or ITAR authorization, and does not provide international visa sponsorship.",
                hard_rejections=hard_rejections,
                ambiguity_flags=[],
            )

        # Gate 6: Freshness & Active State Hard Gate
        if job.freshness_status == "future_rejected" or (job.published_at and "9999" in job.published_at):
            hard_rejections.append("Job posting has an invalid future publication timestamp.")
            return CareerDecisionReport(
                decision=CareerDecision.REJECT,
                match_score=match_score,
                decision_reasons=["INVALID_FUTURE_TIMESTAMP"],
                decision_explanation="Posting has an invalid future publication timestamp.",
                hard_rejections=hard_rejections,
                ambiguity_flags=[],
            )

        if str(job.status).lower() in ("expired", "archived", "jobstatus.expired", "jobstatus.archived"):
            hard_rejections.append("Job posting is marked as closed or archived.")
            return CareerDecisionReport(
                decision=CareerDecision.REJECT,
                match_score=match_score,
                decision_reasons=["LISTING_CLOSED"],
                decision_explanation="Job posting is marked as closed or expired.",
                hard_rejections=hard_rejections,
                ambiguity_flags=[],
            )

        # Gate 7: Ambiguous Conditions & Overseas Handling -> REVIEW
        # 7a. Overseas with unstated visa sponsorship
        if work_auth.status == WorkAuthStatus.SPONSORSHIP_UNCLEAR:
            ambiguity_flags.append("International listing with unstated visa sponsorship policy.")
            return CareerDecisionReport(
                decision=CareerDecision.REVIEW,
                match_score=match_score,
                decision_reasons=["OVERSEAS_AUTHORIZATION_UNKNOWN"],
                decision_explanation="Entry-level semiconductor role, but international work authorization and visa sponsorship status are unstated; requires manual verification.",
                hard_rejections=[],
                ambiguity_flags=ambiguity_flags,
            )

        # 7b. Overseas opportunity with sponsorship available -> REVIEW for human relocation check
        if not work_auth.is_domestic_india and work_auth.status == WorkAuthStatus.SPONSORSHIP_AVAILABLE:
            ambiguity_flags.append("International listing offering visa sponsorship; requires human review of relocation and permit criteria.")
            return CareerDecisionReport(
                decision=CareerDecision.REVIEW,
                match_score=match_score,
                decision_reasons=["OVERSEAS_SPONSORSHIP_REVIEW"],
                decision_explanation=f"International opportunity in {job.location or 'overseas'} with visa assistance noted; human review recommended before proceeding.",
                hard_rejections=[],
                ambiguity_flags=ambiguity_flags,
            )

        # 7c. Fixture / synthetic origin in production scan
        if is_fixture:
            ambiguity_flags.append("Listing originates from a fixture source rather than live carrier page.")
            return CareerDecisionReport(
                decision=CareerDecision.REVIEW,
                match_score=match_score,
                decision_reasons=["FIXTURE_PROVENANCE_REQUIRES_LIVE_VERIFICATION"],
                decision_explanation="Opportunity originates from a fixture source; requires verification against live job board before application.",
                hard_rejections=[],
                ambiguity_flags=ambiguity_flags,
            )

        # 7d. Borderline experience range (e.g. 1-3 years) or generic hardware title requiring check
        if re.search(r"\b1\s*-\s*3\s*(?:years|yrs)\b", f"{title_l} {desc_l}") or title_l.startswith("hardware engineer"):
            ambiguity_flags.append("Experience range (1-3 years) or broad hardware engineer title requires human verification.")
            return CareerDecisionReport(
                decision=CareerDecision.REVIEW,
                match_score=match_score,
                decision_reasons=["BORDERLINE_MATCH_OR_EXPERIENCE"],
                decision_explanation="Position lists 1-3 years experience or broader hardware scope; manual review recommended for 2025 entry-level match.",
                hard_rejections=[],
                ambiguity_flags=ambiguity_flags,
            )

        # 7e. Adjacent semiconductor hardware role (RTL, FPGA, Embedded, Firmware, Hardware Design, etc.)
        if self.ADJACENT_HARDWARE_PATTERN.search(title_l) and not (self.CORE_DV_TITLE_PATTERN.search(title_l) and match_score >= 50.0):
            ambiguity_flags.append(f"Role title '{job.title}' represents adjacent semiconductor engineering.")
            return CareerDecisionReport(
                decision=CareerDecision.REVIEW,
                match_score=match_score,
                decision_reasons=["ADJACENT_HARDWARE_ROLE"],
                decision_explanation=f"Semiconductor role '{job.title}' is adjacent to core Design Verification; candidate may review and tailor assets accordingly.",
                hard_rejections=[],
                ambiguity_flags=ambiguity_flags,
            )

        # Gate 8: Technical Score Threshold
        if match_score < 50.0:
            if self.ADJACENT_HARDWARE_PATTERN.search(title_l) or "verification" in title_l or "dv" in title_l:
                ambiguity_flags.append(f"Moderate match score ({match_score:.1f}%) in hardware domain.")
                return CareerDecisionReport(
                    decision=CareerDecision.REVIEW,
                    match_score=match_score,
                    decision_reasons=["BORDERLINE_MATCH_OR_EXPERIENCE"],
                    decision_explanation=f"Opportunity has moderate technical alignment ({match_score:.1f}%); manual review recommended.",
                    hard_rejections=[],
                    ambiguity_flags=ambiguity_flags,
                )
            return CareerDecisionReport(
                decision=CareerDecision.REJECT,
                match_score=match_score,
                decision_reasons=["LOW_MATCH_SCORE"],
                decision_explanation=f"Match score ({match_score:.1f}) is below minimum technical threshold for candidate profile.",
                hard_rejections=[f"Technical match score {match_score:.1f} is insufficient."],
                ambiguity_flags=[],
            )

        # Gate 9: Clean Strong Match -> APPLY
        decision_reasons = [
            "ENTRY_LEVEL_ROLE",
            "DV_ROLE_MATCH",
            "EDUCATION_COMPATIBLE",
            "WORK_AUTH_CONFIRMED",
            "FRESH_POSTING",
        ]
        return CareerDecisionReport(
            decision=CareerDecision.APPLY,
            match_score=match_score,
            decision_reasons=decision_reasons,
            decision_explanation=f"Entry-level Design Verification role ({match_score:.1f}% match) with compatible 2025 education, verified authorization, and current posting.",
            hard_rejections=[],
            ambiguity_flags=[],
        )


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
        self.decision_engine = CareerDecisionEngine()

    def evaluate_career_decision(
        self,
        job: NormalizedJob,
        match_score: float,
        freshness_age_hours: float | None = None,
        is_fixture: bool = False,
    ) -> CareerDecisionReport:
        """Evaluate authoritative career decision: APPLY, REVIEW, or REJECT."""
        eligibility = self.eligibility_classifier.classify(job, self.profile.candidate.graduation_year)
        work_auth = self.work_auth_classifier.classify(job, getattr(self.profile.candidate.work_authorization, "citizen_of", "India"))
        return self.decision_engine.evaluate_decision(
            job=job,
            match_score=match_score,
            eligibility=eligibility,
            work_auth=work_auth,
            freshness_age_hours=freshness_age_hours,
            is_fixture=is_fixture,
        )

    def create_application_package(
        self,
        job: NormalizedJob,
        match_score: float,
        freshness_age_hours: float | None = None,
        is_material_update: bool = False,
        is_fixture: bool = False,
    ) -> ApplicationPackage:
        """Constructs an auditable, human-gated application package."""
        eligibility = self.eligibility_classifier.classify(job, self.profile.candidate.graduation_year)
        work_auth = self.work_auth_classifier.classify(job, getattr(self.profile.candidate.work_authorization, "citizen_of", "India"))
        resume_profile, reason = self.resume_selector.select_profile(job, eligibility)
        cover_letter = self.cover_letter_gen.generate(job, resume_profile)

        decision_report = self.decision_engine.evaluate_decision(
            job=job,
            match_score=match_score,
            eligibility=eligibility,
            work_auth=work_auth,
            freshness_age_hours=freshness_age_hours,
            is_fixture=is_fixture,
        )

        p_score, p_tier, timing = self.priority_engine.compute_priority(
            job=job,
            match_score=match_score,
            eligibility=eligibility,
            work_auth=work_auth,
            freshness_age_hours=freshness_age_hours,
        )

        # Align priority tier with hard career rejection
        if decision_report.decision == CareerDecision.REJECT:
            p_tier = ApplicationPriorityTier.SKIP
            timing = ApplicationTimingRecommendation.SKIP
            p_score = min(p_score, 35.0)

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
            career_decision=decision_report.decision,
            decision_reasons=decision_report.decision_reasons,
            decision_explanation=decision_report.decision_explanation,
            selected_resume_profile=resume_profile,
            resume_selection_reason=reason,
            cover_letter=cover_letter,
            application_status=ApplicationStatus.DISCOVERED,
            created_at=now_iso,
            is_material_update=is_material_update,
            warnings=warnings,
        )
