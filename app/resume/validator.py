"""Fact Integrity Validator ensuring zero fabricated claims, metrics, or unverified facts in resumes."""

from __future__ import annotations

import re
from typing import ClassVar

from app.profile.models import FactBank, FactCategory
from app.resume.models import FactAuditReport, TailoredResume


class FactIntegrityValidator:
    """Rigorous validator checking that all resume and application claims map to verified candidate FactBank entries."""

    # Patterns representing sensitive or restricted claims that require explicit verified backing
    WORK_AUTH_PATTERNS: ClassVar[list[re.Pattern]] = [
        re.compile(r"\b(?:authorized to work in (?:usa|the united states|us|canada|uk|europe|germany|netherlands|singapore))\b", re.IGNORECASE),
        re.compile(r"\b(?:us citizen|united states citizen|us person|permanent resident|green card holder|security clearance|itar cleared)\b", re.IGNORECASE),
    ]

    UNSUPPORTED_METRIC_PATTERNS: ClassVar[list[re.Pattern]] = [
        re.compile(r"\b(\d+(?:\.\d+)?%\s*(?:functional\s*|code\s*)?coverage)\b", re.IGNORECASE),
        re.compile(r"\b(\d+\s*bugs?\s*(?:found|fixed|closed|resolved|identified))\b", re.IGNORECASE),
        re.compile(r"\b(\d+\+?\s*years?(?:\s+of)?\s+(?:uvm|systemverilog|dv|asic|verification|industry)\s+experience)\b", re.IGNORECASE),
    ]

    def __init__(self, fact_bank: FactBank):
        self.fact_bank = fact_bank

    def validate_fact_ids(self, fact_ids: list[str]) -> tuple[bool, list[str]]:
        """Check if all fact_ids exist in FactBank and are verified."""
        unsupported = []
        for fid in fact_ids:
            fact = self.fact_bank.get_fact(fid)
            if fact is None:
                unsupported.append(f"Fact ID '{fid}' does not exist in Fact Bank.")
            elif not fact.verified:
                unsupported.append(f"Fact ID '{fid}' ('{fact.subject}') is marked unverified.")
        return len(unsupported) == 0, unsupported

    def audit_text(self, text: str) -> tuple[bool, list[str]]:
        """Audit an arbitrary text artifact (e.g. cover letter, notes) against unverified claims and metrics."""
        violations: list[str] = []

        # 1. Work authorization claims check
        for pattern in self.WORK_AUTH_PATTERNS:
            for match in pattern.finditer(text):
                claim = match.group(0)
                # Check if this authorization claim is explicitly backed by a verified fact in FactBank
                backed = any(
                    f.verified and claim.lower() in str(f.value).lower()
                    for f in self.fact_bank.facts
                )
                if not backed:
                    violations.append(f"Unauthorized work authorization / citizenship claim detected: '{claim}'")

        # 2. Exaggerated / ungrounded metrics check
        for pattern in self.UNSUPPORTED_METRIC_PATTERNS:
            for match in pattern.finditer(text):
                metric = match.group(0)
                backed = any(
                    f.verified and metric.lower() in str(f.value).lower()
                    for f in self.fact_bank.facts
                )
                if not backed:
                    violations.append(f"Ungrounded metric claim detected in text: '{metric}'")

        return len(violations) == 0, violations

    def audit_resume(self, resume: TailoredResume) -> FactAuditReport:
        """
        Perform a comprehensive integrity audit on the tailored resume:
        1. All source_fact_ids are verified in FactBank.
        2. All project bullets reference verified Fact IDs.
        3. Skills in resume must exist as verified SkillFacts in FactBank.
        4. No fabricated coverage percentages, bug counts, or years of experience.
        5. Work authorization & citizenship claims must be strictly grounded.
        """
        all_referenced_fids: set[str] = set(resume.source_fact_ids)
        unsupported: list[str] = []
        total_claims = len(all_referenced_fids)

        # Collect fact IDs from education, projects, experience
        for edu in resume.education:
            all_referenced_fids.add(edu.source_fact_id)
        for proj in resume.projects:
            all_referenced_fids.add(proj.source_fact_id)
            for b in proj.bullets:
                all_referenced_fids.update(b.source_fact_ids)
                total_claims += len(b.source_fact_ids)
        for exp in resume.experience:
            all_referenced_fids.add(exp.source_fact_id)
            for b in exp.bullets:
                all_referenced_fids.update(b.source_fact_ids)
                total_claims += len(b.source_fact_ids)

        # 1. Verify all referenced Fact IDs against FactBank
        verified_count = 0
        unverified_count = 0

        for fid in all_referenced_fids:
            fact = self.fact_bank.get_fact(fid)
            if fact is None:
                unsupported.append(f"Unregistered claim: Fact ID '{fid}' not found in candidate Fact Bank.")
                unverified_count += 1
            elif not fact.verified:
                unsupported.append(f"Unverified claim: Fact ID '{fid}' ('{fact.subject}') is unverified.")
                unverified_count += 1
            else:
                verified_count += 1

        # 2. Verify technical skills against verified SKILL facts
        verified_skill_names = set()
        for sf in self.fact_bank.get_facts_by_category(FactCategory.SKILL):
            if sf.verified:
                verified_skill_names.add(sf.subject.lower().strip())
                if isinstance(sf.value, dict):
                    if "skill" in sf.value:
                        verified_skill_names.add(str(sf.value["skill"]).lower().strip())
                    if "skill_name" in sf.value:
                        verified_skill_names.add(str(sf.value["skill_name"]).lower().strip())

        for cat, skills in resume.technical_skills_by_category.items():
            for skill in skills:
                skill_norm = skill.lower().strip()
                if not any(skill_norm == vs or skill_norm in vs or vs in skill_norm for vs in verified_skill_names):
                    unsupported.append(f"Unverified skill claim in category '{cat}': '{skill}' not backed by FactBank.")
                    unverified_count += 1

        # 3. Check for fabricated metrics in bullet texts and summary
        fabricated_metrics: list[str] = []
        full_text_corpus = resume.professional_summary + " " + " ".join(
            b.text for proj in resume.projects for b in proj.bullets
        ) + " " + " ".join(
            b.text for exp in resume.experience for b in exp.bullets
        )

        for pattern in self.UNSUPPORTED_METRIC_PATTERNS:
            for match in pattern.finditer(full_text_corpus):
                metric = match.group(0)
                found_in_facts = any(
                    f.verified and metric.lower() in str(f.value).lower()
                    for f in self.fact_bank.facts
                )
                if not found_in_facts:
                    fabricated_metrics.append(f"Fabricated metric '{metric}' detected in resume.")

        # 4. Work authorization check
        _, auth_violations = self.audit_text(full_text_corpus)
        unsupported.extend(auth_violations)

        is_pass = len(unsupported) == 0 and len(fabricated_metrics) == 0
        integrity_status = "PASS" if is_pass else "FAIL"

        return FactAuditReport(
            total_claims=total_claims,
            verified_claims=verified_count,
            unverified_claims=unverified_count,
            unsupported_claims=unsupported,
            fabricated_metrics_detected=fabricated_metrics,
            integrity_status=integrity_status,
        )
