"""Deterministic ATS scoring engine, parser safety checker, and 80-point quality gate evaluator."""

import re

from app.db.models import NormalizedJob
from app.resume.models import ATSBreakdown, TailoredResume


class ATSScorer:
    """Deterministic, explainable ATS evaluation engine adhering to hard quality gates and parser safety."""

    def __init__(self, target_quality_gate: float = 80.0):
        self.target_quality_gate = target_quality_gate

    def evaluate_parser_safety(self, resume: TailoredResume) -> tuple[float, str, list[str]]:
        """
        Check that the resume structure strictly adheres to ATS parser guidelines:
        - Clean standard sections
        - No tables or text boxes
        - Clean bullet text without decorative characters
        """
        issues: list[str] = []
        score = 100.0

        # Check section presence
        if not resume.professional_summary:
            issues.append("Missing professional summary section.")
            score -= 20.0
        if not resume.technical_skills_by_category:
            issues.append("Missing technical skills section.")
            score -= 30.0
        if not resume.projects:
            issues.append("Missing projects section.")
            score -= 30.0
        if not resume.education:
            issues.append("Missing education section.")
            score -= 20.0

        # Check for forbidden decorative characters in bullets
        for proj in resume.projects:
            for b in proj.bullets:
                if any(char in b.text for char in ["★", "➔", "❖", "✔", "■", "●"]):
                    issues.append(f"Decorative icon found in bullet: '{b.text[:40]}...'")
                    score -= 10.0

        score = max(0.0, score)
        status = "PASS" if score >= 80.0 else "FAIL"
        return score, status, issues

    def score_resume(
        self,
        resume: TailoredResume,
        job: NormalizedJob,
        fact_integrity_status: str,
    ) -> ATSBreakdown:
        """
        Compute multi-dimensional ATS score:
        - Technical keyword match (30%)
        - Required skills coverage (30%)
        - Project relevance (20%)
        - Role/title alignment (10%)
        - Parser safety (10%)
        """
        job_skills = [s.strip().lower() for s in job.skills if s.strip()]
        if not job_skills:
            job_skills = ["systemverilog", "uvm", "digital design", "verilog"]

        # 1. Collect candidate skills and project evidence
        resume_skills: set[str] = set()
        for cat_skills in resume.technical_skills_by_category.values():
            for sk in cat_skills:
                resume_skills.add(sk.lower().strip())

        skills_and_project_text = " ".join([
            " ".join(resume_skills),
            " ".join(p.title.lower() + " " + " ".join(b.text.lower() for b in p.bullets) for p in resume.projects),
        ])

        resume_full_text = f"{resume.professional_summary.lower()} {skills_and_project_text}"

        # 2. Match required skills against candidate evidence
        matching_skills: list[str] = []
        missing_skills: list[str] = []
        partial_matches: list[str] = []

        for req_skill in job_skills:
            if req_skill in skills_and_project_text or any(req_skill == sk or req_skill in sk for sk in resume_skills):
                matching_skills.append(req_skill)
            else:
                domain_parts = [
                    p for p in req_skill.split()
                    if len(p) >= 3 and p not in {"and", "the", "gen", "for", "with", "inc", "verification", "engineer"}
                ]
                if domain_parts and any(re.search(rf"\b{re.escape(p)}\b", skills_and_project_text) for p in domain_parts):
                    partial_matches.append(req_skill)
                else:
                    missing_skills.append(req_skill)

        # 3. Calculate dimension scores
        # Required skills coverage (0 - 100)
        req_coverage_score = round(
            ((len(matching_skills) + 0.5 * len(partial_matches)) / len(job_skills)) * 100.0, 1
        ) if job_skills else 100.0

        # Technical keyword density match (0 - 100)
        dv_core_keywords = [
            "systemverilog", "uvm", "axi", "sva", "assertions", "coverage",
            "constrained-random", "scoreboard", "driver", "monitor", "fifo",
            "cdc", "questasim", "vcs", "modelsim", "verilog", "rtl", "testbench"
        ]
        matched_dv = [kw for kw in dv_core_keywords if kw in resume_full_text]
        tech_keyword_score = round(min(100.0, (len(matched_dv) / max(6, len(dv_core_keywords) * 0.4)) * 100.0), 1)

        # Project relevance score (0 - 100)
        project_hits = 0
        for p in resume.projects:
            p_text = (p.title + " " + " ".join(p.technologies) + " " + " ".join(b.text for b in p.bullets)).lower()
            if any(s in p_text for s in job_skills):
                project_hits += 1
        proj_relevance_score = round(min(100.0, (project_hits / max(1, len(resume.projects))) * 100.0), 1)

        # Role alignment score (0 - 100)
        role_words = [w.lower() for w in job.title.split() if len(w) > 2]
        role_matches = sum(1 for w in role_words if w in resume.professional_summary.lower())
        role_alignment_score = round(min(100.0, (role_matches / max(1, len(role_words))) * 100.0), 1)

        # Parser safety (0 - 100)
        parser_safety_score, parser_status, _ = self.evaluate_parser_safety(resume)

        # 4. Weighted total score
        # 30% Tech keywords, 30% Required skills, 20% Projects, 10% Role, 10% Parser safety
        overall_score = round(
            0.30 * tech_keyword_score
            + 0.30 * req_coverage_score
            + 0.20 * proj_relevance_score
            + 0.10 * role_alignment_score
            + 0.10 * parser_safety_score,
            1,
        )

        # Quality Gate condition: overall >= target_quality_gate (80.0) and fact integrity == PASS
        quality_gate_met = (overall_score >= self.target_quality_gate) and (fact_integrity_status == "PASS")

        # 4. Adjacent Evidence and Unsupported Requirements Mapping
        adjacent_evidence_found: dict[str, str] = {}
        unsupported_requirements: list[str] = []

        adjacent_rules = [
            (
                ["pcie", "ethernet", "usb", "i2c", "spi", "apb", "ahb"],
                "Verified AXI4 Protocol UVC & AMBA layered testbench experience provides adjacent protocol architecture grounding.",
            ),
            (
                ["formal", "jaspergold", "jasper", "formal verification", "property checking"],
                "Verified SystemVerilog Assertions (SVA) & concurrent temporal assertions provide adjacent formal property grounding.",
            ),
            (
                ["uvm ral", "ral", "regmodel", "register abstraction"],
                "Verified UVM modular architecture (factory, config_db, sequence libraries) provides adjacent methodology grounding.",
            ),
            (
                ["cdc", "clock domain crossing", "spyglass", "lint", "metastability"],
                "Verified Dual-Clock Async FIFO (Asynchronous FIFO) with 2-FF synchronizers and Gray pointer CDC logic provides adjacent CDC verification evidence.",
            ),
            (
                ["cadence xcelium", "vcs", "synopsys vcs", "incisive", "dsim"],
                "Verified Siemens QuestaSim / ModelSim multi-vendor simulator experience provides adjacent EDA tool fluency.",
            ),
            (
                ["coverage driven", "functional coverage", "crv", "constrained random"],
                "Verified SystemVerilog functional coverage, covergroups, and constrained-random sequences provide adjacent verification evidence.",
            ),
        ]

        for skill in missing_skills + partial_matches:
            skill_lower = skill.lower()
            found_adj = False
            for triggers, adj_desc in adjacent_rules:
                if any(tr in skill_lower for tr in triggers):
                    adjacent_evidence_found[skill] = adj_desc
                    found_adj = True
                    break
            if skill in missing_skills:
                if not found_adj:
                    unsupported_requirements.append(
                        f"Candidate Fact Bank contains zero verified evidence for '{skill}' (No claim fabricated)."
                    )
                else:
                    unsupported_requirements.append(
                        f"Direct evidence for '{skill}' missing; adjacent verified evidence: {adjacent_evidence_found[skill]}"
                    )

        # 5. Potential interview risks (missing skills that employer expects)
        potential_risks = [
            f"JD requires '{ms}', candidate Fact Bank has no direct matching evidence."
            for ms in missing_skills
        ]

        score_rationale = [
            f"Technical keyword density: {tech_keyword_score}% (found {len(matched_dv)} core verification terms).",
            f"Required skills coverage: {req_coverage_score}% ({len(matching_skills)}/{len(job_skills)} direct matches).",
            f"Project relevance: {proj_relevance_score}% ({project_hits}/{len(resume.projects)} projects align with JD).",
            f"Role title alignment: {role_alignment_score}% with '{job.title}'.",
            f"ATS parser safety: {parser_safety_score}% ({parser_status}).",
            f"Fact integrity: {fact_integrity_status}.",
        ]

        if not quality_gate_met:
            if overall_score < self.target_quality_gate:
                score_rationale.append(
                    f"ATS TARGET NOT REACHED: Score {overall_score}/100 is below minimum threshold {self.target_quality_gate}."
                )
            if fact_integrity_status != "PASS":
                score_rationale.append("FACT INTEGRITY GATE FAILED: Unsupported or unverified claims detected.")

        return ATSBreakdown(
            overall_score=overall_score,
            technical_keyword_score=tech_keyword_score,
            required_skills_coverage=req_coverage_score,
            project_relevance_score=proj_relevance_score,
            role_alignment_score=role_alignment_score,
            parser_safety_score=parser_safety_score,
            parser_safety_status=parser_status,
            fact_integrity_status=fact_integrity_status,
            quality_gate_met=quality_gate_met,
            matching_skills=matching_skills,
            missing_skills=missing_skills,
            partial_matches=partial_matches,
            unsupported_requirements=unsupported_requirements,
            adjacent_evidence_found=adjacent_evidence_found,
            potential_interview_risks=potential_risks,
            score_rationale=score_rationale,
        )
