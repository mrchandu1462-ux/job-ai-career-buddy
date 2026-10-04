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


SENIOR_ROLE_PATTERN = r"\b(?:senior|sr\.?|staff|principal|lead|architect|director|manager|head\s+of|vp)\b"

UNRELATED_ROLE_KEYWORDS = [
    r"\b(?:full\s*stack|web\s*developer|react|angular|node\.js|front[\s-]end|ui[\s-]ux|backend\s*developer|java\s*developer|dotnet|\.net|devops|cloud\s*architect)\b",
    r"\b(?:customer\s*(?:support|service|success)|content\s*moderat(?:or|ion)|bpo|telecaller|sales\s*executive|marketing\s*specialist|talent\s*acquisition|hr\s*recruiter)\b",
    r"\b(?:manual\s*test(?:er|ing)|generic\s*qa|software\s*testing\s*manual|selenium\s*tester)\b",
]

VLSI_OVERRIDE_KEYWORDS = [
    r"\b(?:systemverilog|uvm|sva|verilog|asic|soc|rtl|vlsi|semiconductor|fpga|digital\s*design|questa|vcs|xcelium)\b"
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
        title_lower = job.title.lower()
        desc_lower = (job.description or "").lower()
        combined_text = f"{title_lower} {desc_lower}"

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

        # 2. Seniority & Experience Bounds Filter
        is_senior = bool(re.search(SENIOR_ROLE_PATTERN, title_lower)) and not any(
            t in title_lower for t in ["trainee", "intern", "junior", "entry", "fresher", "get"]
        )
        if is_senior:
            failed.append(
                f"Senior / Staff / Principal / Lead / Architect role title '{job.title}' exceeding entry-level fresher bounds."
            )
        elif job.experience_min is not None and job.experience_min > 2.0:
            failed.append(
                f"Requires {job.experience_min}+ years of experience, exceeding entry-level fresher threshold."
            )
        elif re.search(r"\b(?:3\+|4\+|5\+|7\+|10\+)\s*(?:years?|yrs?)\b", desc_lower) and not re.search(r"\b(?:0-1|0-2|1-2|fresher|entry[\s-]level|2025)\b", desc_lower):
            failed.append("Listing description explicitly mandates 3+ years experience, exceeding entry-level fresher threshold.")
        else:
            exp_text = f"{job.experience_min or 0.0}-{job.experience_max or 1.0} yrs"
            passed.append(f"Experience requirements ({exp_text}) are compatible with fresher profile.")

        # 3. Role Compatibility & Quality Filter
        is_unrelated = any(re.search(pat, combined_text) for pat in UNRELATED_ROLE_KEYWORDS)
        has_vlsi_keywords = any(re.search(pat, combined_text) for pat in VLSI_OVERRIDE_KEYWORDS)

        if is_unrelated and not has_vlsi_keywords:
            failed.append(f"Role title '{job.title}' is classified as non-semiconductor / unrelated software or testing job.")
        else:
            role_matched = any(re.search(pat, title_lower) for pat in RELATED_VLSI_ROLE_KEYWORDS)
            if not role_matched:
                for target_role in self.profile.candidate.target_roles:
                    if target_role.lower() in title_lower or title_lower in target_role.lower():
                        role_matched = True
                        break

            if not role_matched and not has_vlsi_keywords:
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

                    # Check for explicit negative sponsorship signals
                    has_no_sponsorship = (
                        job.visa_sponsorship == "sponsorship_not_supported"
                        or job.visa_status == "sponsorship_not_supported"
                        or bool(
                            re.search(
                                r"\b(?:no\s*(?:visa\s*)?sponsorship|cannot\s*sponsor|not\s*able\s*to\s*sponsor|"
                                r"unable\s*to\s*sponsor|sponsorship\s*(?:is\s*)?not\s*(?:available|provided|offered)|"
                                r"must\s*already\s*have\s*(?:work\s*)?authorization|us\s*citizens?\s*or\s*green\s*card\s*only|"
                                r"citizenship\s*required|without\s*(?:company\s*)?sponsorship)\b",
                                combined_text,
                            )
                        )
                    )
                    if has_no_sponsorship:
                        failed.append(
                            f"Overseas position in {job.country} explicitly requires existing work authorization / does not sponsor visas."
                        )
                    else:
                        passed.append("Flagged for overseas visa sponsorship tracking.")
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
