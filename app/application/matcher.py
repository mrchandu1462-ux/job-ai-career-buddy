"""Application Matcher providing explainable matching factors, skill gaps, and adjacent evidence."""

from app.application.models import ApplicationCandidateMatch
from app.career.repository import CareerRepository
from app.db.models import NormalizedJob
from app.jobs.classifier import RoleClassifier
from app.matching.scorer import JobScoringEngine
from app.profile.models import CandidateProfile, FactBank, FactCategory


class ApplicationMatcher:
    """Computes explainable candidate-job relevance matching with truthful gap and adjacent evidence disclosure."""

    def __init__(
        self,
        profile: CandidateProfile,
        fact_bank: FactBank,
        career_repo: CareerRepository | None = None,
    ):
        self.profile = profile
        self.fact_bank = fact_bank
        self.career_repo = career_repo
        self.scoring_engine = JobScoringEngine(profile, fact_bank, career_repo)
        self.role_classifier = RoleClassifier()

    def match_job(self, job: NormalizedJob) -> ApplicationCandidateMatch:
        """
        Evaluate candidate fit for a job:
        - Calculates 7-dimension score
        - Classifies semiconductor role
        - Compiles explainable positive reasons
        - Compiles skill gaps and truthful adjacent evidence
        """
        match_result = self.scoring_engine.score_job(job)
        role_result = self.role_classifier.classify(job.title, job.description or "")

        reasons_why: list[str] = []
        skill_gaps: list[str] = []
        adjacent_evidence: dict[str, str] = {}

        # 1. Evaluate positive match reasons
        verified_skills = [
            f.subject.lower()
            for f in self.fact_bank.get_facts_by_category(FactCategory.SKILL)
            if f.verified
        ]
        verified_projects = [
            f.subject.lower()
            for f in self.fact_bank.get_facts_by_category(FactCategory.PROJECT)
            if f.verified
        ]

        if "systemverilog" in verified_skills or any("systemverilog" in s for s in verified_skills):
            reasons_why.append("+ SystemVerilog OOP, Classes & Randomization verified proficiency")
        if "uvm" in verified_skills or any("uvm" in s for s in verified_skills):
            reasons_why.append("+ UVM Testbench Architecture & VIP development verified experience")
        if any("axi" in s for s in verified_skills + verified_projects):
            reasons_why.append("+ AXI4 Protocol Interface Verification IP development")
        if any("fifo" in s or "cdc" in s for s in verified_skills + verified_projects):
            reasons_why.append("+ Dual-Clock Async FIFO & Clock Domain Crossing (CDC) verification")
        if self.profile.candidate.graduation_year == 2025:
            reasons_why.append("+ 2025 ECE Graduate Engineer Trainee / Fresher alignment")
        if role_result.relevance_score >= 80.0:
            reasons_why.append(f"+ Direct semiconductor role alignment ({role_result.category.value})")

        # 2. Extract skill gaps and map adjacent evidence
        adjacent_rules = [
            (
                ["pcie", "ethernet", "usb", "i2c", "spi", "apb", "ahb"],
                "Verified AXI4 Protocol UVC & AMBA layered testbench provides adjacent protocol architecture grounding.",
            ),
            (
                ["formal", "jaspergold", "jasper", "formal verification"],
                "Verified SystemVerilog Assertions (SVA) & concurrent assertions provide adjacent formal property grounding.",
            ),
            (
                ["uvm ral", "ral", "regmodel", "register abstraction"],
                "Verified UVM factory, config_db, and sequence libraries provide adjacent methodology grounding.",
            ),
            (
                ["cdc", "clock domain crossing", "spyglass", "lint"],
                "Verified Dual-Clock Async FIFO with 2-FF synchronizers & Gray pointers provides adjacent CDC evidence.",
            ),
            (
                ["cadence xcelium", "vcs", "synopsys vcs", "incisive"],
                "Verified Siemens QuestaSim / ModelSim multi-vendor simulator experience provides adjacent EDA tool fluency.",
            ),
        ]

        missing_skills_list = (
            [sd.skill_name for sd in match_result.breakdown_7d.skill_details if sd.category.value in {"MISSING", "UNKNOWN"}]
            if match_result.breakdown_7d
            else match_result.score_breakdown.missing_skills
        )

        for ms in missing_skills_list:
            skill_gaps.append(ms)
            s_lower = ms.lower()
            for triggers, adj_text in adjacent_rules:
                if any(t in s_lower for t in triggers):
                    adjacent_evidence[ms] = adj_text
                    break

        disqualifications: list[str] = []
        if not match_result.is_eligible:
            disqualifications = match_result.hard_filters.failed_criteria

        return ApplicationCandidateMatch(
            job_id=job.id if job.id is not None else 0,
            company=job.company,
            title=job.title,
            match_score=round(match_result.match_score, 1),
            is_eligible=match_result.is_eligible,
            role_category=role_result.category.value,
            reasons_why=reasons_why,
            skill_gaps=skill_gaps,
            adjacent_evidence=adjacent_evidence,
            disqualification_reasons=disqualifications,
        )
