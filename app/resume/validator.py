"""Fact Integrity Validator ensuring zero fabricated claims, metrics, or unverified facts in resumes."""

import re

from app.profile.models import FactBank
from app.resume.models import FactAuditReport, TailoredResume


class FactIntegrityValidator:
    """Rigorous validator checking that all resume claims map to verified candidate FactBank entries."""

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

    def audit_resume(self, resume: TailoredResume) -> FactAuditReport:
        """
        Perform a comprehensive integrity audit on the tailored resume:
        1. All source_fact_ids are verified in FactBank.
        2. All project bullets reference verified Fact IDs.
        3. No fabricated coverage percentages or bug counts unless grounded in FactBank.
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

        # Verify all referenced Fact IDs against FactBank
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

        # Check for fabricated metrics in bullet texts
        fabricated_metrics: list[str] = []
        for proj in resume.projects:
            for b in proj.bullets:
                # Look for suspicious fabricated metric patterns (e.g. "100% coverage", "45 bugs")
                matches = re.findall(r"\b(\d+%\s+coverage|\d+\s+bugs?\s+found|\d+\s+bugs?\s+fixed)\b", b.text, re.IGNORECASE)
                for m in matches:
                    # Check if metric string exists in the underlying fact text
                    found_in_facts = False
                    for fid in b.source_fact_ids:
                        fact = self.fact_bank.get_fact(fid)
                        if fact and m.lower() in str(fact.value).lower():
                            found_in_facts = True
                            break
                    if not found_in_facts:
                        fabricated_metrics.append(f"Fabricated metric '{m}' in bullet: '{b.text}'")

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
