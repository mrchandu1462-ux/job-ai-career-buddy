"""Deterministic job relevance scoring engine grounded in verified Fact Bank claims."""

import sqlite3

from app.career.repository import CareerRepository
from app.db.models import NormalizedJob
from app.jobs.classifier import RoleClassifier
from app.matching.filters import HardFilterEngine
from app.matching.models import (
    HardFilterResult,
    JobMatchResult,
    JobScoreBreakdown7D,
    SkillMatchDetail,
    SoftScoreBreakdown,
    TechnicalSkillCategory,
)
from app.profile.models import CandidateProfile, FactBank, FactCategory

CORE_VERIFICATION_WEIGHTS: dict[str, float] = {
    "SystemVerilog": 18.0,
    "UVM": 18.0,
    "Verilog": 12.0,
    "SVA": 10.0,
    "Functional Coverage": 10.0,
    "Constrained Random": 10.0,
    "AXI": 8.0,
    "APB": 8.0,
    "AHB": 8.0,
    "FIFO": 8.0,
    "CDC": 8.0,
    "Digital Design": 8.0,
    "RTL": 8.0,
    "OVM": 5.0,
    "UVM RAL": 8.0,
}

TOOL_WEIGHTS: dict[str, float] = {
    "VCS": 5.0,
    "Questa": 5.0,
    "Linux": 5.0,
    "Python": 5.0,
    "C/C++": 4.0,
    "Tcl": 3.0,
    "Perl": 3.0,
    "Incisive/Xcelium": 4.0,
    "Formal Verification": 4.0,
}


class JobScoringEngine:
    """Computes transparent, explainable 0-100 relevance scores using verified candidate facts."""

    def __init__(
        self,
        profile: CandidateProfile,
        fact_bank: FactBank,
        career_repo: CareerRepository | None = None,
    ):
        self.profile = profile
        self.fact_bank = fact_bank
        self.career_repo = career_repo
        self.filter_engine = HardFilterEngine(profile)
        self.role_classifier = RoleClassifier()
        self.verified_skill_set, self.skill_fact_map = self._extract_verified_skills_and_map()
        self.verified_project_techs = self._extract_verified_project_technologies()

    def _extract_verified_skills_and_map(self) -> tuple[set[str], dict[str, str]]:
        """Extract verified skill names and map each lowercase skill name to its supporting fact_id."""
        skills: set[str] = set()
        fact_map: dict[str, str] = {}

        # 1. Process SKILL category facts first (highest precedence)
        for fact in self.fact_bank.get_verified_facts():
            if fact.category == FactCategory.SKILL:
                subj = fact.subject.strip()
                skills.add(subj)
                fact_map[subj.lower()] = fact.fact_id

                if isinstance(fact.value, dict):
                    topics = fact.value.get("topics", [])
                    if isinstance(topics, list):
                        for t in topics:
                            t_str = str(t).strip()
                            skills.add(t_str)
                            fact_map[t_str.lower()] = fact.fact_id

        # 2. Process PROJECT and other category facts if not already mapped
        for fact in self.fact_bank.get_verified_facts():
            if fact.category != FactCategory.SKILL:
                subj = fact.subject.strip()
                skills.add(subj)
                if subj.lower() not in fact_map:
                    fact_map[subj.lower()] = fact.fact_id

                if isinstance(fact.value, dict):
                    techs = fact.value.get("technologies", [])
                    if isinstance(techs, list):
                        for t in techs:
                            t_str = str(t).strip()
                            skills.add(t_str)
                            if t_str.lower() not in fact_map:
                                fact_map[t_str.lower()] = fact.fact_id

        return skills, fact_map

    def _extract_verified_project_technologies(self) -> set[str]:
        """Extract technologies verified within candidate project facts."""
        techs: set[str] = set()
        for fact in self.fact_bank.get_verified_facts():
            if fact.category == FactCategory.PROJECT and isinstance(fact.value, dict):
                p_techs = fact.value.get("technologies", [])
                if isinstance(p_techs, list):
                    for t in p_techs:
                        techs.add(str(t).strip().lower())
        return techs

    def _candidate_has_skill(self, skill_name: str) -> bool:
        """Check if a skill exists in candidate's verified skills."""
        skill_lower = skill_name.lower()
        return any(skill_lower == s.lower() or skill_lower in s.lower() for s in self.verified_skill_set)

    def _get_supporting_fact_id(self, skill_name: str) -> str | None:
        """Find the fact ID supporting a given skill."""
        skill_lower = skill_name.lower()
        for s_name, f_id in self.skill_fact_map.items():
            if skill_lower == s_name or skill_lower in s_name or s_name in skill_lower:
                return f_id
        return None

    def score_job(self, job: NormalizedJob) -> JobMatchResult:
        """Run hard eligibility filter and compute 7-dimension explainable relevance score."""
        hard_filter: HardFilterResult = self.filter_engine.evaluate(job)

        matching_skills: list[str] = []
        missing_skills: list[str] = []
        reasons: list[str] = []
        gaps: list[str] = []
        skill_details: list[SkillMatchDetail] = []

        # ---------------------------------------------------------------------
        # 1. Backward-Compatible SoftScore Calculation (0-100 legacy format)
        # ---------------------------------------------------------------------
        core_score = 0.0
        for skill in job.skills:
            if skill in CORE_VERIFICATION_WEIGHTS:
                weight = CORE_VERIFICATION_WEIGHTS[skill]
                if self._candidate_has_skill(skill):
                    core_score += weight
                    matching_skills.append(skill)
                    reasons.append(f"+ {skill} (Verified Candidate Fact)")
                    fact_id = self._get_supporting_fact_id(skill)
                    skill_details.append(
                        SkillMatchDetail(
                            skill_name=skill,
                            category=TechnicalSkillCategory.VERIFIED_MATCH,
                            evidence_fact_id=fact_id,
                            notes="Verified candidate skill claim.",
                            weight=weight,
                        )
                    )
                else:
                    missing_skills.append(skill)
                    gaps.append(f"- {skill} requested by employer")
                    skill_details.append(
                        SkillMatchDetail(
                            skill_name=skill,
                            category=TechnicalSkillCategory.MISSING,
                            evidence_fact_id=None,
                            notes="Skill requested in job description but not in verified candidate fact bank.",
                            weight=weight,
                        )
                    )

        if not job.skills and ("Verification" in job.title or "DV" in job.title):
            if self._candidate_has_skill("SystemVerilog"):
                core_score += 15.0
                matching_skills.append("SystemVerilog")
                reasons.append("+ SystemVerilog (Inferred target DV requirement)")
            if self._candidate_has_skill("UVM"):
                core_score += 15.0
                matching_skills.append("UVM")
                reasons.append("+ UVM (Inferred target DV requirement)")

        skill_score = min(60.0, round(core_score, 1))

        # Tool & Scripting Score
        tool_score_accum = 0.0
        for skill in job.skills:
            if skill in TOOL_WEIGHTS:
                weight = TOOL_WEIGHTS[skill]
                if self._candidate_has_skill(skill):
                    tool_score_accum += weight
                    if skill not in matching_skills:
                        matching_skills.append(skill)
                    reasons.append(f"+ {skill} tool / language match")
                    fact_id = self._get_supporting_fact_id(skill)
                    skill_details.append(
                        SkillMatchDetail(
                            skill_name=skill,
                            category=TechnicalSkillCategory.VERIFIED_MATCH,
                            evidence_fact_id=fact_id,
                            notes="Verified tool / programming competency.",
                            weight=weight,
                        )
                    )
                else:
                    if skill not in missing_skills:
                        missing_skills.append(skill)
                    gaps.append(f"- {skill} tool experience preferred")
                    skill_details.append(
                        SkillMatchDetail(
                            skill_name=skill,
                            category=TechnicalSkillCategory.MISSING,
                            evidence_fact_id=None,
                            notes="Preferred tool not found in verified facts.",
                            weight=weight,
                        )
                    )

        if self._candidate_has_skill("Python") and "Python" not in matching_skills:
            tool_score_accum += 3.0
            reasons.append("+ Python (Verified General Scripting)")
        if self._candidate_has_skill("Linux") and "Linux" not in matching_skills:
            tool_score_accum += 3.0
            reasons.append("+ Linux (Verified Environment Familiarity)")

        tools_score = min(20.0, round(tool_score_accum, 1))

        # Location Scoring with Tier 1 & Tier 2 support
        location_score = 0.0
        loc_str = (job.location or "").lower()
        country_str = (job.country or "").lower()

        india_t1 = getattr(self.profile.candidate.locations, "india_tier1", ["Bengaluru", "Hyderabad", "Chennai"])
        india_t2 = getattr(
            self.profile.candidate.locations,
            "india_tier2",
            ["Pune", "Noida", "Gurugram", "Ahmedabad", "Mysuru", "Kochi", "Mumbai"],
        )
        overseas_pref = getattr(
            self.profile.candidate.locations,
            "overseas_priority_countries",
            ["USA", "Canada", "UK", "Germany", "Netherlands", "Singapore", "Taiwan", "Japan", "South Korea", "Ireland", "Australia", "UAE", "France", "Sweden", "Switzerland"],
        )

        if any(hub.lower() in loc_str for hub in india_t1):
            location_score = 10.0
            reasons.append(f"+ Priority Tier 1 Tech Hub: {job.location}")
        elif any(hub.lower() in loc_str for hub in india_t2):
            location_score = 8.5
            reasons.append(f"+ Priority Tier 2 Tech Hub: {job.location}")
        elif country_str == "india" or "india" in loc_str:
            location_score = 8.0
            reasons.append(f"+ India Location: {job.location or 'India'}")
        elif any(c.lower() in country_str or c.lower() in loc_str for c in overseas_pref):
            location_score = 7.0
            reasons.append(f"+ Target Overseas Market: {job.country or job.location}")
        elif hard_filter.is_overseas:
            location_score = 5.5
            reasons.append(f"+ Overseas Opportunity: {job.country}")
        else:
            location_score = 5.0

        # Role Fit Scoring with Tier Hierarchy
        title_lower = job.title.lower()
        if any(term in title_lower for term in ["asic verification", "soc verification", "functional verification", "design verification", "dv engineer"]):
            role_fit_score = 10.0
            reasons.append("+ Direct Tier 1 Design Verification role fit")
        elif any(term in title_lower for term in ["verification intern", "dv intern", "rtl intern", "vlsi intern", "rtl design", "digital design"]):
            role_fit_score = 8.5
            reasons.append("+ Tier 2 RTL / Verification Internship role fit")
        elif any(term in title_lower for term in ["graduate engineer trainee", "get", "trainee", "semiconductor graduate"]):
            role_fit_score = 8.0
            reasons.append("+ Tier 3 Graduate / Trainee role fit")
        elif "verification" in title_lower or "dv" in title_lower:
            role_fit_score = 9.0
            reasons.append("+ Verification role fit")
        else:
            role_fit_score = 5.0

        # Watchlist boost
        watchlist_boost = 0.0
        if job.is_watchlist:
            watchlist_boost = 5.0
            reasons.append(f"+ Watchlisted Company: {job.company}")

        total_legacy_score = min(100.0, round(skill_score + tools_score + location_score + role_fit_score + watchlist_boost, 1))

        # ---------------------------------------------------------------------
        # 2. Enhanced 7-Dimension Explainable Score Breakdown
        # ---------------------------------------------------------------------
        # Dim 1: Role Relevance (Max 20)
        role_class_res = self.role_classifier.classify(job.title, job.description or "")
        d1_role = round(role_class_res.relevance_score, 1)

        # Dim 2: Technical Skill Match (Max 25)
        # Scaled from core verification skills (max 25)
        matched_core_count = sum(
            1 for s in matching_skills if s in CORE_VERIFICATION_WEIGHTS or s in ["SystemVerilog", "UVM", "SVA", "Verilog"]
        )
        if matched_core_count >= 4:
            d2_tech = 25.0
        elif matched_core_count >= 3:
            d2_tech = 22.0
        elif matched_core_count >= 2:
            d2_tech = 18.0
        elif matched_core_count >= 1:
            d2_tech = 14.0
        else:
            d2_tech = 8.0

        # Dim 3: Project Alignment (Max 20)
        # Check candidate verified project tech overlap with JD (e.g. APB, AXI, FIFO, CDC, UVM)
        project_tech_matches = 0
        job_text_lower = (f"{job.title} {job.description or ''} {' '.join(job.skills)}").lower()
        for p_tech in self.verified_project_techs:
            if p_tech in job_text_lower:
                project_tech_matches += 1

        if project_tech_matches >= 3:
            d3_proj = 20.0
        elif project_tech_matches >= 2:
            d3_proj = 16.0
        elif project_tech_matches >= 1:
            d3_proj = 12.0
        else:
            d3_proj = 8.0

        # Dim 4: Fresher / Experience Fit (Max 10)
        exp_min = job.experience_min or 0.0
        exp_max = job.experience_max or 1.0
        if exp_min == 0.0 and exp_max <= 1.0:
            d4_fresher = 10.0
        elif exp_min <= 1.0:
            d4_fresher = 8.5
        elif exp_min <= 2.0:
            d4_fresher = 6.0
        else:
            d4_fresher = 2.0

        # Dim 5: Location Preference (Max 10)
        d5_loc = location_score

        # Dim 6: Interview Knowledge Relevance (Max 10)
        d6_interview = 5.0
        if self.career_repo:
            try:
                historical_qs = self.career_repo.query_interview_questions(company=job.company)
                if historical_qs:
                    d6_interview = 10.0
                else:
                    topic_qs = self.career_repo.query_interview_questions(limit=5)
                    if topic_qs:
                        d6_interview = 8.0
            except (sqlite3.Error, AttributeError, ValueError):
                d6_interview = 5.0
        else:
            # Baseline availability for standard DV topics in Career KB
            d6_interview = 8.0

        # Dim 7: Freshness / Source Quality (Max 5)
        d7_freshness = 5.0
        if job.source.startswith("careers_") or "company" in job.source:
            d7_freshness = 5.0
        elif job.source.startswith("board_"):
            d7_freshness = 4.5
        else:
            d7_freshness = 4.0

        # Total 7D score
        total_7d = min(100.0, round(d1_role + d2_tech + d3_proj + d4_fresher + d5_loc + d6_interview + d7_freshness, 1))

        # Itemized reasons and gaps for 7D
        itemized_reasons = [
            f"Role Relevance ({d1_role}/20): {role_class_res.justification}",
            f"Technical Match ({d2_tech}/25): {len(matching_skills)} verified technical skills matched ({', '.join(matching_skills[:4])}).",
            f"Project Alignment ({d3_proj}/20): {project_tech_matches} verified project technologies aligned.",
            f"Fresher Fit ({d4_fresher}/10): Experience range ({exp_min}-{exp_max} yrs) compatible with 2025 graduate.",
            f"Location Preference ({d5_loc}/10): {job.location or job.country or 'India'}.",
            f"Interview Relevance ({d6_interview}/10): Knowledge base context available for target company and topics.",
            f"Freshness & Source ({d7_freshness}/5): Source provenance '{job.source}'.",
        ]

        itemized_gaps = [f"- {s} requested by employer but not verified in fact bank" for s in missing_skills]

        breakdown_7d = JobScoreBreakdown7D(
            role_relevance=d1_role,
            technical_match=d2_tech,
            project_alignment=d3_proj,
            fresher_fit=d4_fresher,
            location_preference=d5_loc,
            interview_relevance=d6_interview,
            freshness_quality=d7_freshness,
            total_score=total_7d,
            role_classification=role_class_res,
            skill_details=skill_details,
            itemized_reasons=itemized_reasons,
            itemized_gaps=itemized_gaps,
        )

        # Legacy final match score
        final_match_score = total_legacy_score if hard_filter.is_eligible else 0.0

        score_breakdown = SoftScoreBreakdown(
            skill_score=skill_score,
            tools_score=tools_score,
            location_score=location_score,
            role_fit_score=role_fit_score,
            total_score=total_legacy_score,
            matching_skills=sorted(set(matching_skills)),
            missing_skills=sorted(set(missing_skills)),
            reasons=reasons,
            gaps=gaps,
        )

        explanation = (
            f"JOB MATCH: {int(final_match_score)}/100 | "
            f"Role: {d1_role}/20 | Tech: {d2_tech}/25 | Projects: {d3_proj}/20 | "
            f"Fresher: {d4_fresher}/10 | Loc: {d5_loc}/10 | Interview: {d6_interview}/10 | Freshness: {d7_freshness}/5 | "
            f"Eligible: {'YES' if hard_filter.is_eligible else 'NO'}"
        )

        return JobMatchResult(
            job_id=job.id if job.id is not None else 0,
            company=job.company,
            title=job.title,
            location=job.location,
            country=job.country,
            is_eligible=hard_filter.is_eligible,
            match_score=final_match_score,
            hard_filters=hard_filter,
            score_breakdown=score_breakdown,
            breakdown_7d=breakdown_7d,
            is_overseas=hard_filter.is_overseas,
            requires_sponsorship=hard_filter.requires_sponsorship,
            explanation=explanation,
        )
