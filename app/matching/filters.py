"""Hard eligibility filtering engine evaluating candidate constraints deterministically."""

import re

from app.db.models import NormalizedJob
from app.matching.models import EligibilityStatus, HardFilterResult
from app.profile.models import CandidateProfile

RELATED_VLSI_ROLE_KEYWORDS = [
    r"\bverification\b",
    r"\bdv\b",
    r"\basic\b",
    r"\bsoc\b",
    r"\brtl\b",
    r"\bvlsi\b",
    r"\bdigital\s*design\b",
    r"\bsemiconductor\b",
    r"\bhardware\s*engineer\b",
    r"\bgtop\b",
    r"\bget\b",
    r"\bgraduate\s*engineer\s*trainee\b",
    r"\bfpga\b",
]


class HardFilterEngine:
    """Evaluates non-negotiable candidate constraints (graduation year, experience bounds, locations, roles)."""

    def __init__(self, profile: CandidateProfile):
        self.profile = profile

    def evaluate(self, job: NormalizedJob) -> HardFilterResult:
        """Run all hard eligibility rules and return pass/fail status with explainable reasons."""
        passed: list[str] = []
        failed: list[str] = []

        candidate_grad_year = self.profile.candidate.graduation_year

        # 1. Graduation Year Filter
        if job.graduation_year_min is not None and candidate_grad_year < job.graduation_year_min:
            failed.append(
                f"Graduation year ({candidate_grad_year}) is earlier than required minimum ({job.graduation_year_min})."
            )
        elif job.graduation_year_max is not None and candidate_grad_year > job.graduation_year_max:
            failed.append(
                f"Graduation year ({candidate_grad_year}) is later than required maximum ({job.graduation_year_max})."
            )
        else:
            passed.append(f"Graduation year ({candidate_grad_year}) is eligible.")

        # 2. Experience Bounds Filter
        if job.experience_min is not None and job.experience_min > 2.0:
            failed.append(
                f"Requires {job.experience_min}+ years of experience, exceeding entry-level fresher threshold."
            )
        else:
            exp_text = f"{job.experience_min or 0.0}-{job.experience_max or 1.0} yrs"
            passed.append(f"Experience requirements ({exp_text}) are compatible with fresher profile.")

        # 3. Role Compatibility Filter
        title_lower = job.title.lower()
        role_matched = any(re.search(pat, title_lower) for pat in RELATED_VLSI_ROLE_KEYWORDS)

        # Also check against explicit profile target roles
        if not role_matched:
            for target_role in self.profile.candidate.target_roles:
                if target_role.lower() in title_lower or title_lower in target_role.lower():
                    role_matched = True
                    break

        if not role_matched:
            failed.append(f"Role title '{job.title}' is not compatible with target VLSI/DV fresher profile.")
        else:
            passed.append(f"Role title '{job.title}' matches target semiconductor verification profile.")

        # 4. Location & Overseas Sponsorship Filter
        is_overseas = False
        requires_sponsorship = False

        job_country = (job.country or "").strip().lower()
        if job_country and job_country != "india":
            is_overseas = True
            if not self.profile.candidate.locations.overseas_enabled:
                failed.append(f"Job is located overseas ({job.country}), but overseas discovery is disabled.")
            else:
                passed.append(f"Overseas listing ({job.country}) allowed by candidate preferences.")
                if self.profile.candidate.work_authorization.requires_sponsorship_overseas:
                    requires_sponsorship = True
                    passed.append("Flagged for explicit overseas visa sponsorship tracking.")
        else:
            passed.append(f"Domestic India listing ({job.location or 'India'}).")

        is_eligible = len(failed) == 0

        if is_eligible:
            status = EligibilityStatus.ELIGIBLE
            explanation = f"Eligible: meets 2025 graduation year, experience (<=2.0 yrs), and target VLSI role criteria ({len(passed)} checks passed)."
        else:
            status = EligibilityStatus.INELIGIBLE
            explanation = f"Ineligible: failed {len(failed)} hard requirement(s) -> {'; '.join(failed)}"

        return HardFilterResult(
            is_eligible=is_eligible,
            status=status,
            passed_criteria=passed,
            failed_criteria=failed,
            is_overseas=is_overseas,
            requires_sponsorship=requires_sponsorship,
            explanation=explanation,
        )
