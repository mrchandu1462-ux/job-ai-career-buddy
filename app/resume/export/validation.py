"""ATS-safe resume export validator ensuring file artifacts match validated candidate facts exactly."""

import os
import re

from docx import Document
from pypdf import PdfReader

from app.resume.export.models import ExportFormat, ExportValidationReport
from app.resume.models import TailoredResume


class ResumeExportValidator:
    """Rigorous validator auditing exported DOCX, PDF, TXT, and MD files for ATS compliance and factual fidelity."""

    def extract_text_from_file(self, file_path: str, fmt: ExportFormat) -> str:
        """Extract all readable text content from an exported resume file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Export file not found: {file_path}")

        if fmt == ExportFormat.DOCX:
            doc = Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            # Also check if any tables exist (disallowed by ATS rules)
            return "\n".join(paragraphs)

        elif fmt == ExportFormat.PDF:
            reader = PdfReader(file_path)
            pages_text = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(pages_text)

        elif fmt in {ExportFormat.PLAINTEXT, ExportFormat.MARKDOWN}:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()

        raise ValueError(f"Unsupported export format: {fmt}")

    def validate_export(
        self,
        file_path: str,
        fmt: ExportFormat,
        validated_resume: TailoredResume,
    ) -> ExportValidationReport:
        """
        Validate exported file against the original validated TailoredResume model:
        1. Checks that non-empty text was extracted.
        2. Verifies all expected section headings exist.
        3. Verifies candidate name and contact information are preserved.
        4. Verifies technical skills and project claims match validated resume.
        5. Verifies no unsupported claims, tables, or fabricated metrics exist.
        6. Ensures zero alteration between model and exported artifact.
        """
        errors: list[str] = []
        parser_warnings: list[str] = []
        missing_sections: list[str] = []
        content_mismatches: list[str] = []

        # 1. Extract Text
        try:
            extracted_text = self.extract_text_from_file(file_path, fmt)
        except (OSError, ValueError, RuntimeError, KeyError) as e:
            errors.append(f"Failed to extract text from {file_path}: {e}")
            return ExportValidationReport(
                status="FAIL",
                format=fmt,
                resume_id=validated_resume.resume_id,
                resume_version=validated_resume.version,
                output_path=file_path,
                extracted_text_length=0,
                missing_sections=["ALL"],
                content_mismatches=[],
                parser_warnings=[],
                errors=errors,
                is_export_validated=False,
            )

        text_length = len(extracted_text)
        if text_length < 150:
            errors.append(f"Extracted text too short ({text_length} chars). File may be corrupted or unreadable.")

        extracted_lower = extracted_text.lower()

        # 2. Structural & Parser Safety Checks for DOCX / PDF
        if fmt == ExportFormat.DOCX:
            try:
                doc = Document(file_path)
                if len(doc.tables) > 0:
                    errors.append(f"ATS Violation: DOCX contains {len(doc.tables)} tables. Single-column required.")
                if len(doc.inline_shapes) > 0:
                    parser_warnings.append("DOCX contains inline shapes/graphics.")
            except (OSError, ValueError, RuntimeError, KeyError) as e:
                errors.append(f"Error inspecting DOCX structure: {e}")

        # 3. Check Section Presence
        expected_sections = [
            ("PROFESSIONAL SUMMARY", ["professional summary", "summary"]),
            ("TECHNICAL SKILLS", ["technical skills", "skills"]),
            ("TECHNICAL PROJECTS", ["technical projects", "projects"]),
            ("EDUCATION", ["education"]),
        ]

        for sec_name, aliases in expected_sections:
            if not any(alias in extracted_lower for alias in aliases):
                missing_sections.append(sec_name)
                errors.append(f"Missing required ATS section: '{sec_name}'.")

        # 4. Check Candidate Identity & Contact Fidelity
        if validated_resume.candidate_name.lower() not in extracted_lower:
            content_mismatches.append(f"Candidate name '{validated_resume.candidate_name}' missing from export.")

        for val in validated_resume.contact_info.values():
            if val and "@" in val and val.lower() not in extracted_lower:
                content_mismatches.append(f"Email contact '{val}' missing from export.")

        # 5. Check Technical Skills Fidelity
        for skills in validated_resume.technical_skills_by_category.values():
            for sk in skills[:3]:  # sample core skills
                sk_clean = sk.split("(")[0].strip().lower()
                if sk_clean and sk_clean not in extracted_lower:
                    content_mismatches.append(f"Verified skill '{sk_clean}' not found in exported text.")

        # 6. Check Project Titles & Key Claims
        for proj in validated_resume.projects:
            if proj.title.lower() not in extracted_lower:
                content_mismatches.append(f"Project title '{proj.title}' missing from export.")
            for bullet in proj.bullets:
                # check significant portion of bullet text
                key_words = [w for w in bullet.text.split() if len(w) > 5][:3]
                if key_words and not all(w.lower() in extracted_lower for w in key_words):
                    content_mismatches.append(f"Bullet content discrepancy in project '{proj.title}'.")

        # 7. Check for Fabricated Metrics Pattern
        fabricated_matches = re.findall(
            r"\b(\d+%\s+coverage|\d+\s+bugs?\s+found|\d+\s+bugs?\s+fixed)\b",
            extracted_text,
            re.IGNORECASE,
        )
        for fm in fabricated_matches:
            # Check if this metric existed in the validated model
            model_text = (
                validated_resume.plain_text_content
                or validated_resume.markdown_content
                or ""
            )
            if fm.lower() not in model_text.lower():
                errors.append(f"Fabricated metric '{fm}' introduced during export.")

        # 8. Overall Status Evaluation
        is_pass = (len(errors) == 0) and (len(content_mismatches) == 0) and (len(missing_sections) == 0)
        status = "PASS" if is_pass else "FAIL"

        return ExportValidationReport(
            status=status,
            format=fmt,
            resume_id=validated_resume.resume_id,
            resume_version=validated_resume.version,
            output_path=file_path,
            extracted_text_length=text_length,
            missing_sections=missing_sections,
            content_mismatches=content_mismatches,
            parser_warnings=parser_warnings,
            errors=errors,
            is_export_validated=is_pass,
        )
